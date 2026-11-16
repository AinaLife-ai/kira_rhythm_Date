from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from lunar_python import Solar

from .models import KRDError
from .timeutils import parse_date

HOLIDAY_URLS = (
    "https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/{year}.json",
    "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json",
)
HOLIDAY_TTL = 6 * 3600
DATA_ROOT = Path(__file__).resolve().parent / "data" / "holidays"


class CalendarService:
    """Offline lunar calendar with versioned statutory-holiday enrichment."""

    def __init__(self, store, ttl_seconds: int = HOLIDAY_TTL):
        self.store = store
        self.ttl_seconds = int(ttl_seconds)
        self._locks: dict[int, asyncio.Lock] = {}
        self._refreshes: dict[int, asyncio.Task] = {}
        self._retry_after: dict[int, float] = {}
        self._ensured: set[int] = set()

    def set_ttl(self, seconds: int) -> None:
        self.ttl_seconds = max(60, int(seconds))

    @staticmethod
    def _validate_payload(payload: dict[str, Any], year: int) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("year") != year or not isinstance(payload.get("days"), list):
            raise KRDError("invalid_holiday_data", "Holiday payload has an invalid year or days collection")
        if len(payload["days"]) > 100 or not isinstance(payload.get("papers", []), list):
            raise KRDError("invalid_holiday_data", "Holiday payload is too large or has invalid papers")
        for row in payload["days"]:
            if (not isinstance(row, dict) or type(row.get("isOffDay")) is not bool or
                    not str(row.get("name", "")).strip() or len(str(row.get("name", ""))) > 40):
                raise KRDError("invalid_holiday_data", "Holiday day has invalid name or isOffDay")
            day = parse_date(str(row.get("date", ""))).isoformat()
            if not day.startswith(f"{year}-"):
                raise KRDError("invalid_holiday_data", "Holiday day is outside its declared year")
        return payload

    async def _bundled(self, year: int) -> dict[str, Any]:
        path = DATA_ROOT / f"{year}.json"
        if not path.is_file():
            return {"payload": {"year": year, "days": [], "papers": []}, "source": "unavailable",
                    "status": "unavailable", "fetched_at": 0}
        payload = self._validate_payload(json.loads(await asyncio.to_thread(path.read_text)), year)
        return {"payload": payload, "source": "holiday-cn-bundled", "status": "bundled", "fetched_at": 0}

    async def _cached(self, year: int) -> dict[str, Any] | None:
        cached = await self.store.get_setting(f"calendar:holiday:{year}", None)
        if not isinstance(cached, dict) or not isinstance(cached.get("payload"), dict):
            return None
        try:
            self._validate_payload(cached["payload"], year)
        except KRDError:
            return None
        return cached

    async def year(self, year: int, *, allow_network: bool = True, force_refresh: bool = False) -> dict[str, Any]:
        cached = await self._cached(year)
        now = time.time()
        if cached and not force_refresh and (not allow_network or now - cached.get("fetched_at", 0) < self.ttl_seconds):
            result = dict(cached)
            if now - result.get("fetched_at", 0) >= self.ttl_seconds:
                result["status"] = "stale"
            return result
        if not allow_network:
            return await self._bundled(year)
        if not cached and not force_refresh and now < self._retry_after.get(year, 0):
            return await self._bundled(year)
        lock = self._locks.setdefault(year, asyncio.Lock())
        async with lock:
            cached = await self._cached(year)
            if cached and not force_refresh and time.time() - cached.get("fetched_at", 0) < self.ttl_seconds:
                return cached
            try:
                result = await self._download(year)
                await self.store.put_setting(f"calendar:holiday:{year}", result)
                self._retry_after.pop(year, None)
                return result
            except Exception:
                self._retry_after[year] = time.time() + 900
                if cached:
                    return {**cached, "status": "stale"}
                return await self._bundled(year)

    async def _download(self, year: int) -> dict[str, Any]:
        last_error = None
        async with httpx.AsyncClient(timeout=5, follow_redirects=True,
                                     headers={"Accept": "application/json", "User-Agent": "KiraRhythmDate/1.1"}) as client:
            for template in HOLIDAY_URLS:
                try:
                    response = await client.get(template.format(year=year))
                    response.raise_for_status()
                    payload = self._validate_payload(response.json(), year)
                    return {"payload": payload, "source": "holiday-cn", "status": "fresh", "fetched_at": time.time(),
                            "source_url": template.format(year=year)}
                except Exception as exc:
                    last_error = exc
        raise KRDError("holiday_unavailable", f"Unable to update {year} holiday data: {type(last_error).__name__}")

    def ensure_year(self, year: int) -> None:
        """Read-through warmup: never waits for the network."""
        if year in self._ensured:
            return
        self._ensured.add(year)
        async def inspect() -> None:
            cached = await self._cached(year)
            if cached:
                return
            bundled = await self._bundled(year)
            if bundled.get("status") != "unavailable":
                return
            self.refresh_soon(year)
        asyncio.create_task(inspect(), name=f"krd_calendar_ensure:{year}")

    def refresh_soon(self, year: int) -> None:
        task = self._refreshes.get(year)
        if task and not task.done():
            return
        task = asyncio.create_task(self.year(year), name=f"krd_calendar:{year}")
        self._refreshes[year] = task

        def finished(completed: asyncio.Task) -> None:
            if self._refreshes.get(year) is completed:
                self._refreshes.pop(year, None)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)

    async def close(self) -> None:
        tasks = list(self._refreshes.values())
        self._refreshes.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    @lru_cache(maxsize=4096)
    def _solar(day: str) -> dict[str, Any]:
        solar = Solar.fromYmd(*[int(part) for part in day.split("-")])
        lunar = solar.getLunar()
        solar_festivals = list(solar.getFestivals()) + list(solar.getOtherFestivals())
        lunar_festivals = list(lunar.getFestivals()) + list(lunar.getOtherFestivals())
        solar_term = lunar.getJieQi()
        lunar_day = lunar.getDayInChinese()
        if lunar.getDay() == 1:
            lunar_day = f"{lunar.getMonthInChinese()}月"
        display = solar_term or (lunar_festivals[0] if lunar_festivals else None) or \
            (solar_festivals[0] if solar_festivals else lunar_day)
        return {
            "date": day, "lunar": {"text": lunar.toString(), "month": lunar.getMonthInChinese(),
                                   "day": lunar_day, "year_ganzhi": lunar.getYearInGanZhi()},
            "solar_term": solar_term,
            "solar_festivals": solar_festivals, "lunar_festivals": lunar_festivals,
            "display": display,
        }

    @staticmethod
    def _with_holiday(base: dict[str, Any], holiday: dict[str, Any] | None) -> dict[str, Any]:
        result = dict(base)
        result["holiday"] = ({"name": holiday["name"], "is_off_day": holiday["isOffDay"]} if holiday else None)
        if holiday:
            result["suggested_day_type"] = "holiday" if holiday["isOffDay"] else "adjusted_workday"
            result["display"] = holiday["name"] if holiday["isOffDay"] else f"{holiday['name']}·调班"
        else:
            weekday = parse_date(base["date"]).weekday()
            result["suggested_day_type"] = "weekend" if weekday >= 5 else "weekday"
        return result

    async def day(self, day: str, *, allow_network: bool = False) -> dict[str, Any]:
        day = parse_date(day).isoformat()
        year = int(day[:4])
        info = await self.year(year, allow_network=allow_network)
        holiday = next((row for row in info["payload"]["days"] if row["date"] == day), None)
        result = self._with_holiday(self._solar(day), holiday)
        result["data_status"] = info["status"]
        return result

    async def range(self, start: str, end: str, *, allow_network: bool = False) -> dict[str, Any]:
        start = parse_date(start).isoformat()
        end = parse_date(end).isoformat()
        if start > end or (parse_date(end) - parse_date(start)).days > 366:
            raise KRDError("invalid_calendar_range", "Expected an ascending range of at most 367 days")
        years = list(range(int(start[:4]), int(end[:4]) + 1))
        for year in years:
            self.ensure_year(year)
        infos = {year: await self.year(year, allow_network=allow_network) for year in years}
        days = []
        current = parse_date(start)
        while current.isoformat() <= end:
            day = current.isoformat()
            info = infos[current.year]
            holiday = next((row for row in info["payload"]["days"] if row["date"] == day), None)
            result = self._with_holiday(self._solar(day), holiday)
            result["data_status"] = info["status"]
            days.append(result)
            current += timedelta(days=1)
        sources = {str(year): {"status": info["status"], "source": info["source"], "fetched_at": info["fetched_at"],
                               "papers": info["payload"].get("papers", [])} for year, info in infos.items()}
        return {"start": start, "end": end, "days": days, "sources": sources}
