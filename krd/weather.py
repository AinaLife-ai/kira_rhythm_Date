from __future__ import annotations

import asyncio
import hashlib
import math
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .store import Store, dumps, loads

WMO = {0: "晴", 1: "大部晴朗", 2: "局部多云", 3: "阴", 45: "雾", 48: "雾凇", 51: "小毛毛雨", 53: "毛毛雨", 55: "浓毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨", 71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒", 80: "小阵雨", 81: "阵雨", 82: "强阵雨", 85: "小阵雪", 86: "阵雪", 95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹"}

WEATHER_CREDENTIAL_FIELDS = {
    "weatherapi": ("weatherapi_key",),
    "visualcrossing": ("visualcrossing_key",),
    "qweather": ("qweather_key",),
    "weatherbit": ("weatherbit_key",),
    "openweather": ("openweather_key",),
    "met_norway": (),
    "nws": (),
    "open_meteo": (),
    "bright_sky": (),
}


class WeatherService:
    def __init__(self, store: Store, ctx, plugin_cfg: dict[str, Any] | None = None):
        self.store = store
        self.ctx = ctx
        self.plugin_cfg = plugin_cfg or {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._refreshes: dict[str, asyncio.Task] = {}

    def refresh_soon(self, persona_id: str) -> None:
        current = self._refreshes.get(persona_id)
        if current and not current.done():
            return
        task = asyncio.create_task(self.summary(persona_id), name=f"krd_weather:{persona_id}")
        self._refreshes[persona_id] = task

        def finished(completed: asyncio.Task) -> None:
            if self._refreshes.get(persona_id) is completed:
                self._refreshes.pop(persona_id, None)
            if not completed.cancelled():
                completed.exception()  # Consume failures; callers receive cache states.

        task.add_done_callback(finished)

    async def close(self) -> None:
        tasks = list(self._refreshes.values())
        self._refreshes.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _client(self, timeout: float = 3.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"Accept-Encoding": "gzip, deflate"})

    @staticmethod
    async def _get(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
        response = await client.get(url, **kwargs)
        response.raise_for_status()
        return response

    async def _ua(self, persona_id: str) -> str:
        stored = await self.store.get_setting(f"weather_credentials:{persona_id}", {})
        contact = str((stored.get("contact") if isinstance(stored, dict) else "") or self.plugin_cfg.get("weather_contact", "")).strip()
        return contact or "KiraRhythmDate/1.0 https://github.com/znq19/kira_rhythm_Date"

    async def geocode(self, name: str, persona_id: str = "") -> list[dict[str, Any]]:
        config = await self.store.get_config(persona_id) if persona_id else None
        provider = (config or {}).get("weather", {}).get("provider", "open_meteo")
        if provider == "qweather":
            try:
                key = await self._credential("qweather_key", persona_id)
                return await self._qweather_geocode(name, key)
            except Exception:
                # Keep location search usable while the user is switching keys.
                pass
        return await self._open_meteo_geocode(name)

    async def _open_meteo_geocode(self, name: str) -> list[dict[str, Any]]:
        raw = str(name or "").strip()
        tokens = [part for part in raw.replace("，", " ").replace(",", " ").split() if part]
        candidates = [raw]
        if tokens:
            candidates.extend([tokens[0], tokens[-1], tokens[0] + "市", tokens[-1] + "市",
                               tokens[0] + "县", tokens[-1] + "县"])
        candidates = list(dict.fromkeys(item for item in candidates if item))
        rows = []
        async with self._client(6) as client:
            for candidate in candidates:
                response = await self._get(client, "https://geocoding-api.open-meteo.com/v1/search",
                                           params={"name": candidate, "count": 50, "language": "zh", "format": "json"})
                response.raise_for_status()
                for row in response.json().get("results", []):
                    item = {
                        "id": row.get("id"), "name": row.get("name") or "",
                        "country": row.get("country", ""), "country_code": row.get("country_code", ""),
                        "admin1": row.get("admin1", ""), "admin2": row.get("admin2", ""),
                        "admin3": row.get("admin3", ""), "admin4": row.get("admin4", ""),
                        "latitude": row.get("latitude"), "longitude": row.get("longitude"),
                        "timezone": row.get("timezone", "auto"), "feature_code": row.get("feature_code", ""),
                        "population": row.get("population") or 0, "source": "open_meteo",
                    }
                    if item["id"] is not None and item["latitude"] is not None:
                        rows.append(item)
        # If the user typed a region plus a city, filter by the extra tokens.
        context = tokens[1:] if len(tokens) > 1 else []
        if context:
            filtered = [row for row in rows if any(str(token).lower() in " ".join(str(row.get(key, "")) for key in
                ("country", "admin1", "admin2", "admin3", "admin4")).lower() for token in context)]
            if filtered:
                rows = filtered
        unique = {}
        for row in rows:
            unique[(row["name"], round(float(row["latitude"]), 5), round(float(row["longitude"]), 5))] = row
        def rank(row):
            base = tokens[0] if tokens else raw
            admin = " ".join(str(row.get(key, "")) for key in ("country", "admin1", "admin2", "admin3", "admin4"))
            cityish = 0 if row["name"] in {base + "市", base + "城区", base + "区"} else 1
            admin_match = 0 if base and base in admin else 1
            exact = 0 if row["name"] == raw else 1
            country = 0 if row.get("country_code") == "CN" or not any("\u4e00" <= char <= "\u9fff" for char in raw) else 1
            feature = {"PPLA": 0, "PPLA2": 0, "PPLA3": 1, "PPLA4": 2, "PPL": 3}.get(str(row.get("feature_code")), 4)
            return (country, cityish, admin_match, exact, feature, -int(row.get("population") or 0), row["name"])
        return sorted(unique.values(), key=rank)[:20]

    async def _qweather_geocode(self, name: str, key: str) -> list[dict[str, Any]]:
        async with self._client(8) as client:
            response = await self._get(client, "https://geoapi.qweather.com/v2/city/lookup",
                                       params={"location": name, "key": key, "lang": "zh", "range": "cn"})
            response.raise_for_status()
            rows = response.json().get("location", [])
        result = []
        for row in rows:
            try:
                lat, lon = float(row["lat"]), float(row["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            result.append({
                "id": row.get("id"), "name": row.get("name", ""), "country": row.get("country", "中国"),
                "country_code": "CN", "admin1": row.get("adm1", ""), "admin2": row.get("adm2", ""),
                "admin3": row.get("adm3", ""), "admin4": row.get("adm4", ""),
                "latitude": lat, "longitude": lon, "timezone": row.get("tz", "auto"),
                "feature_code": "", "source": "qweather",
            })
        return result[:20]

    async def summary(self, persona_id: str, *, allow_network: bool = True) -> dict[str, Any]:
        config = await self.store.get_config(persona_id)
        weather = config["weather"]
        mode = weather.get("mode", "off")
        if mode == "off":
            return {"mode": "off"}
        result: dict[str, Any] = {"mode": mode}
        location = weather.get("locations", {}).get(persona_id) or weather.get("locations", {}).get("default") or {}
        if mode in {"virtual", "hybrid"}:
            result["virtual"] = self.virtual(persona_id, weather.get("virtual", {}))
        if mode in {"real", "hybrid"}:
            if not location:
                result["real"] = {"status": "location_required"}
            else:
                result["real"] = await self._cached_current(persona_id, location, weather, allow_network=allow_network)
        return result

    async def _cached_current(self, persona_id: str, location: dict[str, Any], config: dict[str, Any], *,
                              allow_network: bool = True) -> dict[str, Any]:
        provider = config.get("provider", "open_meteo")
        key = f"current:{provider}:{round(float(location['latitude']), 4)}:{round(float(location['longitude']), 4)}"
        row = await self.store.one("SELECT * FROM weather_cache WHERE cache_key=?", (key,))
        timestamp = __import__('time').time()
        if row and row["expires_at"] > timestamp:
            return loads(row["payload_json"], {"status": "cache_error"})
        if not allow_network:
            if row:
                stale = loads(row["payload_json"], {})
                stale["status"] = "stale"
                return stale
            return {"status": "pending", "provider": provider}
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            row = await self.store.one("SELECT * FROM weather_cache WHERE cache_key=?", (key,))
            if row and row["expires_at"] > timestamp:
                return loads(row["payload_json"], {"status": "cache_error"})
            try:
                data = await self._fetch(provider, location, float(config.get("timeout_seconds", 3)), persona_id)
                data["status"] = "fresh"
                await self.store.execute(
                    "INSERT INTO weather_cache(cache_key,payload_json,fetched_at,expires_at) VALUES(?,?,?,?) "
                    "ON CONFLICT(cache_key) DO UPDATE SET payload_json=excluded.payload_json,fetched_at=excluded.fetched_at,expires_at=excluded.expires_at",
                    (key, dumps(data), timestamp, data.get("expires_at") or timestamp + int(config.get("current_ttl_seconds", 1800))))
                return data
            except Exception as exc:
                if row:
                    stale = loads(row["payload_json"], {})
                    stale["status"] = "stale"
                    return stale
                return {"status": "unavailable", "provider": provider, "reason": type(exc).__name__}

    async def _fetch(self, provider: str, location: dict[str, Any], timeout: float, persona_id: str = "") -> dict[str, Any]:
        lat, lon = float(location["latitude"]), float(location["longitude"])
        async with self._client(timeout) as client:
            if provider == "open_meteo":
                response = await self._get(client,"https://api.open-meteo.com/v1/forecast", params={
                    "latitude": lat, "longitude": lon, "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
                    "timezone": "auto", "forecast_days": 1})
                data = response.json()
                current = data.get("current", {})
                daily = data.get("daily", {})
                return self._normal(provider, location, current.get("time"), current.get("temperature_2m"), current.get("apparent_temperature"),
                                    WMO.get(current.get("weather_code"), str(current.get("weather_code"))), current.get("wind_speed_10m"),
                                    (daily.get("temperature_2m_min") or [None])[0], (daily.get("temperature_2m_max") or [None])[0],
                                    (daily.get("precipitation_probability_max") or [None])[0], (daily.get("sunrise") or [None])[0], (daily.get("sunset") or [None])[0])
            if provider == "met_norway":
                response = await self._get(client,"https://api.met.no/weatherapi/locationforecast/2.0/compact", params={"lat": round(lat, 4), "lon": round(lon, 4)}, headers={"User-Agent": await self._ua(persona_id)})
                data = response.json()
                point = data["properties"]["timeseries"][0]
                details = point["data"]["instant"]["details"]
                summary = point["data"].get("next_1_hours", {}).get("summary", {}).get("symbol_code", "")
                result = self._normal(provider, location, point["time"], details.get("air_temperature"), None, summary.replace("_", " "), details.get("wind_speed"))
                if response.headers.get("Expires"):
                    result["expires_at"] = parsedate_to_datetime(response.headers["Expires"]).timestamp()
                return result
            if provider == "nws":
                headers = {"User-Agent": await self._ua(persona_id), "Accept": "application/geo+json"}
                point = (await self._get(client,f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}", headers=headers)).json()
                forecast_url = point["properties"]["forecast"]
                data = (await self._get(client,forecast_url, headers=headers)).json()
                period = data["properties"]["periods"][0]
                return self._normal(provider, location, period.get("startTime"), period.get("temperature"), None,
                                    period.get("shortForecast"), period.get("windSpeed"), detailed=period.get("detailedForecast"))
            if provider == "bright_sky":
                response = await self._get(client,"https://api.brightsky.dev/current_weather", params={"lat": lat, "lon": lon})
                data = response.json().get("weather", {})
                return self._normal(provider, location, data.get("timestamp"), data.get("temperature"), None,
                                    data.get("condition"), data.get("wind_speed"), detailed=data.get("icon"))
            if provider == "weatherapi":
                key = await self._credential("weatherapi_key", persona_id)
                response = await self._get(client,"https://api.weatherapi.com/v1/forecast.json", params={"key": key, "q": f"{lat},{lon}", "days": 1, "aqi": "no", "alerts": "no"})
                data = response.json()
                current, day = data["current"], data["forecast"]["forecastday"][0]["day"]
                return self._normal(provider, location, current.get("last_updated"), current.get("temp_c"), current.get("feelslike_c"),
                                    current.get("condition", {}).get("text"), current.get("wind_kph"), day.get("mintemp_c"), day.get("maxtemp_c"), day.get("daily_chance_of_rain"))
            if provider == "visualcrossing":
                key = await self._credential("visualcrossing_key", persona_id)
                response = await self._get(client,f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/today", params={"unitGroup": "metric", "key": key, "contentType": "json"})
                data = response.json()
                current, day = data.get("currentConditions", {}), data.get("days", [{}])[0]
                return self._normal(provider, location, current.get("datetime"), current.get("temp"), current.get("feelslike"), current.get("conditions"), current.get("windspeed"), day.get("tempmin"), day.get("tempmax"), day.get("precipprob"), day.get("sunrise"), day.get("sunset"))
            if provider == "qweather":
                key = await self._credential("qweather_key", persona_id)
                response = await self._get(client,"https://devapi.qweather.com/v7/weather/now", params={"location": f"{lon},{lat}", "key": key})
                data = response.json().get("now", {})
                return self._normal(provider, location, data.get("obsTime"), data.get("temp"), data.get("feelsLike"), data.get("text"), data.get("windSpeed"))
            if provider == "weatherbit":
                key = await self._credential("weatherbit_key", persona_id)
                response = await self._get(client,"https://api.weatherbit.io/v2.0/current", params={"lat": lat, "lon": lon, "key": key})
                data = response.json().get("data", [{}])[0]
                return self._normal(provider, location, data.get("ob_time"), data.get("temp"), data.get("app_temp"), data.get("weather", {}).get("description"), data.get("wind_spd"))
            if provider == "openweather":
                key = await self._credential("openweather_key", persona_id)
                response = await self._get(client,"https://api.openweathermap.org/data/3.0/onecall", params={"lat": lat, "lon": lon, "exclude": "minutely,hourly,alerts", "units": "metric", "appid": key})
                data = response.json()
                current, day = data.get("current", {}), data.get("daily", [{}])[0]
                return self._normal(provider, location, current.get("dt"), current.get("temp"), current.get("feels_like"), current.get("weather", [{}])[0].get("description"), current.get("wind_speed"), day.get("temp", {}).get("min"), day.get("temp", {}).get("max"), day.get("pop"))
            raise ValueError(f"Unknown weather provider: {provider}")

    async def _credential(self, name: str, persona_id: str) -> str:
        stored = await self.store.get_setting(f"weather_credentials:{persona_id}", {})
        value = stored.get(name) if isinstance(stored, dict) else None
        if not value:
            nested = self.plugin_cfg.get("weather_credentials", {})
            value = nested.get(name) if isinstance(nested, dict) else None
        value = value or self.plugin_cfg.get(name)
        if not value:
            raise ValueError(f"Missing credential: {name}")
        return str(value)

    async def credential_status(self, persona_id: str) -> dict[str, Any]:
        stored = await self.store.get_setting(f"weather_credentials:{persona_id}", {})
        stored = stored if isinstance(stored, dict) else {}
        nested = self.plugin_cfg.get("weather_credentials", {})
        nested = nested if isinstance(nested, dict) else {}
        return {
            "providers": {provider: {field: bool(stored.get(field) or nested.get(field) or self.plugin_cfg.get(field))
                                      for field in fields}
                          for provider, fields in WEATHER_CREDENTIAL_FIELDS.items()},
            "contact": bool(stored.get("contact") or self.plugin_cfg.get("weather_contact")),
        }

    async def save_credentials(self, persona_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        providers = payload.get("providers", {})
        if not isinstance(providers, dict):
            raise ValueError("weather credentials must be an object")
        stored = await self.store.get_setting(f"weather_credentials:{persona_id}", {})
        stored = dict(stored) if isinstance(stored, dict) else {}
        changed = set()
        for provider, values in providers.items():
            if provider not in WEATHER_CREDENTIAL_FIELDS:
                raise ValueError(f"Unknown weather provider: {provider}")
            if not isinstance(values, dict):
                raise ValueError(f"weather credentials for {provider} must be an object")
            allowed = set(WEATHER_CREDENTIAL_FIELDS[provider])
            for field, value in values.items():
                if field not in allowed:
                    raise ValueError(f"Unknown credential field: {field}")
                text = str(value or "").strip()
                if len(text) > 1000:
                    raise ValueError("weather credential is too long")
                if text:
                    stored[field] = text
                else:
                    stored.pop(field, None)
                changed.add(provider)
        if "contact" in payload:
            contact = str(payload.get("contact") or "").strip()
            if len(contact) > 500:
                raise ValueError("weather contact is too long")
            stored["contact"] = contact
        await self.store.put_setting(f"weather_credentials:{persona_id}", stored)
        for provider in changed:
            await self.store.execute("DELETE FROM weather_cache WHERE cache_key LIKE ?", (f"current:{provider}:%",))
        return await self.credential_status(persona_id)

    @staticmethod
    def _normal(provider: str, location: dict[str, Any], observed: Any, temperature: Any, apparent: Any,
                condition: Any, wind: Any, low: Any = None, high: Any = None, rain: Any = None,
                sunrise: Any = None, sunset: Any = None, detailed: Any = None) -> dict[str, Any]:
        return {"provider": provider, "location": location.get("name", "自定义地点"), "observed_at": observed,
                "temperature": temperature, "apparent_temperature": apparent, "condition": condition,
                "wind_speed": wind, "temperature_min": low, "temperature_max": high,
                "precipitation_probability": rain, "sunrise": sunrise, "sunset": sunset, "detail": detailed,
                "source": "real"}

    def virtual(self, persona_id: str, config: dict[str, Any]) -> dict[str, Any]:
        seed = f"{config.get('seed', 'krd')}:{persona_id}:{datetime.now().date().isoformat()}"
        digest = hashlib.sha256(seed.encode()).digest()
        climate = config.get("climate", "temperate")
        profiles = {
            "temperate": (5, 29, ["晴", "多云", "阴", "小雨"]),
            "island": (16, 30, ["晴", "海风", "阵雨", "多云"]),
            "rainforest": (20, 32, ["小雨", "雷阵雨", "多云", "潮湿"]),
            "snow": (-24, 5, ["晴", "小雪", "大雪", "阴"]),
            "desert": (2, 39, ["晴", "燥热", "大风", "晴朗"]),
            "floating_city": (8, 23, ["云海", "晴", "薄雾", "流光雨"]),
        }
        low, high, conditions = profiles.get(climate, profiles["temperate"])
        day_of_year = datetime.now().timetuple().tm_yday
        seasonal = math.sin((day_of_year - 80) / 365 * math.tau)
        midpoint = (low + high) / 2 + seasonal * min(8, (high - low) / 4)
        temperature = round(midpoint + ((digest[0] / 255) - 0.5) * 6, 1)
        condition = conditions[digest[1] % len(conditions)]
        return {"source": "virtual", "location": config.get("location", "未命名幻想地点"), "climate": climate,
                "temperature": temperature, "apparent_temperature": round(temperature + (digest[2] % 5 - 2), 1),
                "condition": condition, "temperature_min": round(temperature - 3 - digest[3] % 3, 1),
                "temperature_max": round(temperature + 3 + digest[4] % 4, 1),
                "precipitation_probability": digest[5] % 101, "wind_speed": round(1 + digest[6] % 45 / 5, 1)}
