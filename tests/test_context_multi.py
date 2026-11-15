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
