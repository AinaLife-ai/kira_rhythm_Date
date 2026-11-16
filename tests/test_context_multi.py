from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from krd.calendar import CalendarService
from krd.llm_format import prepare_llm_payload
from tests.fakes import FakeRuntime


@pytest.mark.asyncio
async def test_calendar_and_multiple_day_types_are_compact_and_separate(monkeypatch):
    root = __import__("pathlib").Path(__import__("tempfile").mkdtemp(prefix="krd-context-"))
    runtime = FakeRuntime(root)
    await runtime.store.initialize()
    runtime.context_builder.calendar = CalendarService(runtime.store)
    runtime.context_builder.host_timezone = lambda: 'Asia/Shanghai'
    day = (datetime.now().date() + timedelta(days=1)).isoformat()
    await runtime.store.update_config("persona-a", {
        "weather": {"mode": "off"},
        "calendar_context": {"holiday": True, "adjusted_workday": True, "festivals": True, "solar_terms": True},
        "daily_limits": {"min_items": 2, "max_items": 8},
    }, await runtime.store.config_revision("persona-a"))
    await runtime.store.save_day_type("persona-a", {
        "id": "payday", "name": "发薪日",
        "rules": {"dates": [day], "priority": 20},
        "config": {"overrides": {"planning_prompt": "安排与收入有关的事。"}},
    })
    await runtime.store.save_day_type("persona-a", {
        "id": "prayer", "name": "祈祷日",
        "rules": {"dates": [day], "priority": 10},
        "config": {"overrides": {"planning_prompt": "留出安静祷告的时间。"}},
    })
    result = await runtime.plans.apply_plan("persona-a", {
        "date": day, "title": "样本",
        "blocks": [{"title": "一天", "items": [
            {"title": "一", "schedule": {"type": "exact", "at": "09:00"}},
            {"title": "二", "schedule": {"type": "exact", "at": "10:00"}},
        ]}],
    }, actor="user", expected_revision=0)
    plan = result["plan"]
    assert await runtime.plans.resolve_day_type("persona-a", day) == "prayer"
    names = [item["name"] for item in await runtime.plans.resolve_day_types("persona-a", day)]
    assert names == ["祈祷日", "发薪日"]
    meta = {"run_id": "run_private", "trigger_id": "trg_private", "kind": "planning",
            "persona_id": "persona-a", "date": day, "item_id": "", "plan_id": plan["id"], "reason": "手动"}
    prompt = await runtime.context_builder.planning_prompt(meta)
    assert "祈祷日" in prompt and "发薪日" in prompt
    assert "run_private" not in prompt and "trg_private" not in prompt
    assert '"weather"' not in prompt and '"timezone"' not in prompt
    assert '"daily_limits":{"min_items":2' in prompt
    assert '"day_type":{"id"' not in prompt
    assert '"suggested_day_type"' not in prompt
    await runtime.close()


def test_llm_payload_drops_empty_values_but_keeps_meaningful_false():
    compact = prepare_llm_payload({
        "empty": "", "none": None, "empty_list": [], "empty_dict": {},
        "off": False, "zero": 0, "keep": "x", "timezone": "Asia/Shanghai",
    }, "Asia/Shanghai", "Asia/Shanghai")
    assert compact == {"off": False, "zero": 0, "keep": "x"}

@pytest.mark.asyncio
async def test_short_item_reference_resolves_within_persona():
    from pathlib import Path
    import tempfile
    from tests.fakes import FakeRuntime

    runtime = FakeRuntime(Path(tempfile.mkdtemp(prefix="krd-short-id-")))
    await runtime.store.initialize()
    day = (datetime.now().date() + timedelta(days=1)).isoformat()
    result = await runtime.plans.apply_plan("persona-a", {
        "date": day, "title": "短 ID",
        "blocks": [{"title": "组", "items": [
            {"title": "一", "schedule": {"type": "exact", "at": "09:00"}},
            {"title": "二", "schedule": {"type": "exact", "at": "10:00"}},
        ]}],
    }, actor="user", expected_revision=0)
    item = result["plan"]["blocks"][0]["items"][0]
    short = item["id"].split("_", 1)[1][:12]
    updated = await runtime.plans.update_item("persona-a", short, {"title": "短 ID 更新"}, actor="bot")
    assert any(item["title"] == "短 ID 更新" for block in updated["plan"]["blocks"] for item in block["items"])
    await runtime.close()

@pytest.mark.asyncio
async def test_disabled_custom_day_type_is_kept_but_not_resolved():
    from pathlib import Path
    import tempfile
    from tests.fakes import FakeRuntime

    runtime = FakeRuntime(Path(tempfile.mkdtemp(prefix="krd-disabled-day-type-")))
    await runtime.store.initialize()
    day = datetime.now().date().isoformat()
    await runtime.store.save_day_type("persona-a", {
        "id": "temporary_day", "name": "临时日型",
        "rules": {"dates": [day], "priority": 5},
        "config": {"color": "#123456"},
    })
    assert (await runtime.plans.resolve_day_type("persona-a", day)) == "temporary_day"
    await runtime.store.update_config("persona-a", {
        "day_type_enabled": {"temporary_day": False},
    }, await runtime.store.config_revision("persona-a"))
    assert (await runtime.plans.resolve_day_type("persona-a", day)) == ""
    entries = await runtime.store.list_day_types("persona-a")
    assert any(entry["id"] == "temporary_day" for entry in entries)
    await runtime.close()
