from __future__ import annotations

from pathlib import Path

import pytest

from krd.store import Store
from krd.weather import WeatherService


class _Ctx:
    def get_timezone(self):
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Shanghai")


async def _service(tmp_path: Path, weather: dict) -> tuple[Store, WeatherService]:
    store = Store(tmp_path / "db")
    await store.initialize()
    await store.update_config("default", {"weather": weather}, 0)
    return store, WeatherService(store, _Ctx())


def _virtual(**extra):
    return {"mode": "virtual", "virtual": {"seed": "forecast-test", "climate": "temperate", "location": "测试城"}, **extra}


@pytest.mark.asyncio
async def test_forecast_has_target_periods_and_future_days(tmp_path):
    store, service = await _service(tmp_path, _virtual())
    forecast = await service.forecast("default", "2026-11-17", 3, allow_network=False)
    assert forecast["status"] == "virtual"
    dates = [day["date"] for day in forecast["days"]]
    assert dates[:3] == ["2026-11-17", "2026-11-18", "2026-11-19"]
    assert all(len(day["periods"]) == 8 for day in forecast["days"])
    await store.close()


@pytest.mark.asyncio
async def test_planning_target_detail_and_future_detail_switches(tmp_path):
    store, service = await _service(tmp_path, _virtual(target_detail=False, future_detail=True))
    weather = await service.context_weather("default", "2026-11-17", kind="plan", allow_network=False)
    assert "periods" not in weather["target"]
    assert all(isinstance(day, dict) and "periods" in day for day in weather["forecast"])
    await store.close()


@pytest.mark.asyncio
async def test_item_next_can_be_disabled_and_has_no_provenance_fields(tmp_path):
    store, service = await _service(tmp_path, _virtual(item_next=False))
    weather = await service.context_weather("default", "2026-11-17", kind="item", allow_network=False)
    assert "next" not in weather
    assert not {"mode", "timezone", "source", "observed_at", "status"} & set(weather)
    await store.close()


@pytest.mark.asyncio
async def test_chat_current_and_forecast_are_separate(tmp_path):
    store, service = await _service(tmp_path, _virtual(chat_current=False, chat_forecast=True, chat_forecast_days=2))
    weather = await service.context_weather("default", "2026-11-17", kind="chat", allow_network=False)
    assert "now" not in weather and "today" not in weather
    assert len(weather["forecast"]) == 2
    assert all("periods" not in day for day in weather["forecast"])
    await store.close()


@pytest.mark.asyncio
async def test_future_target_does_not_fall_back_to_current(tmp_path):
    store, service = await _service(tmp_path, {"mode": "real", "provider": "open_meteo", "locations": {}})
    weather = await service.context_weather("default", "2026-11-17", kind="plan", allow_network=False)
    assert weather is None
    await store.close()


def test_new_weather_defaults():
    from krd.config import DEFAULT_CONFIG
    weather = DEFAULT_CONFIG["weather"]
    assert weather["chat_current"] is True
    assert weather["chat_forecast"] is False
    assert weather["chat_forecast_days"] == 2
    assert weather["target_detail"] is True
    assert weather["future_detail"] is False
    assert weather["item_next"] is True
    assert DEFAULT_CONFIG["calendar_refresh_hours"] == 6
