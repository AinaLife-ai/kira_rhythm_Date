from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from krd.calendar import CalendarService
from .fakes import FakeRuntime


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    value.calendar = CalendarService(value.store)
    value.plans.calendar = value.calendar
    value.context_builder.calendar = value.calendar
    yield value
    await value.close()


@pytest.mark.asyncio
async def test_lunar_solar_term_and_statutory_holiday(runtime):
    day = await runtime.calendar.day("2026-02-17")
    assert day["lunar"]["day"] == "正月" or "正月初一" in day["lunar"]["text"]
    assert day["holiday"] == {"name": "春节", "is_off_day": True}
    assert day["suggested_day_type"] == "holiday"
    assert day["lunar_festivals"] == ["春节"]
    assert day["data_status"] == "bundled"


@pytest.mark.asyncio
async def test_adjusted_workday_and_solar_term(runtime):
    adjusted = await runtime.calendar.day("2026-01-04")
    assert adjusted["suggested_day_type"] == "adjusted_workday"
    assert adjusted["holiday"]["is_off_day"] is False
    term = await runtime.calendar.day("2026-02-04")
    assert term["solar_term"] == "立春" and term["display"] == "立春"


@pytest.mark.asyncio
async def test_solar_festivals_are_available_to_bot_and_ui(runtime):
    day = await runtime.calendar.day("2026-06-21")
    assert "父亲节" in day["solar_festivals"]
    assert day["solar_term"] == "夏至"
    result = await runtime.calendar.range("2026-06-20", "2026-06-22")
    assert len(result["days"]) == 3 and result["sources"]["2026"]["papers"]


@pytest.mark.asyncio
async def test_fresh_remote_payload_is_cached_with_official_papers(runtime):
    payload = {"year": 2026, "papers": ["https://www.gov.cn/example"], "days": [
        {"name": "元旦", "date": "2026-01-01", "isOffDay": True}]}
    runtime.calendar._download = AsyncMock(return_value={
        "payload": payload, "source": "holiday-cn", "status": "fresh", "fetched_at": __import__("time").time()})
    fresh = await runtime.calendar.year(2026, force_refresh=True)
    assert fresh["source"] == "holiday-cn"
    cached = await runtime.calendar.year(2026)
    assert cached["payload"]["papers"] == ["https://www.gov.cn/example"]
    runtime.calendar._download.assert_awaited_once()


@pytest.mark.asyncio
async def test_custom_day_type_rule_beats_statutory_suggestion(runtime):
    await runtime.store.save_day_type("persona-a", {"id": "family_day", "name": "家庭日", "rules": {
        "dates": ["2027-01-01"], "priority": 1}, "config": {}})
    resolved = await runtime.plans.resolve_day_type("persona-a", "2027-01-01")
    assert resolved == "family_day"
    assert await runtime.plans.resolve_day_type("persona-a", "2027-01-02") == ""
    await runtime.store.update_config("persona-a", {"base_day_types": {"holiday": True}}, 0)
    assert await runtime.plans.resolve_day_type("persona-a", "2027-01-02") == "holiday"
