from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio

from krd.models import KRDError
from .fakes import FakeRuntime


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    yield value
    await value.close()


def payload_for(day, items):
    return {"date": day, "title": "规则测试", "blocks": [{"title": "组", "items": items}]}


def exact(title, clock, **extra):
    return {"title": title, "schedule": {"type": "exact", "at": clock}, "target": "qq:dm:10001", **extra}


@pytest.mark.asyncio
async def test_day_type_overrides_prompt_and_quota(runtime):
    day = (datetime.now().date() + timedelta(days=1)).isoformat()
    await runtime.store.save_day_type("persona-a", {"id": "solo_day", "name": "独处日", "rules": {"dates": [day]},
        "config": {"overrides": {"min_items": 1, "planning_prompt": "今天只需要一件真正想做的事"}}})
    result = await runtime.plans.apply_plan("persona-a", payload_for(day, [exact("独处", "09:00")]), expected_revision=0)
    assert result["plan"]["day_type_id"] == "solo_day"
    effective = await runtime.plans.effective_config("persona-a", "solo_day")
    assert effective["min_items"] == 1 and effective["planning_prompt"].startswith("今天只需要")


@pytest.mark.asyncio
async def test_quiet_delivery_and_blocked_execution_are_distinct(runtime):
    day = (datetime.now().date() + timedelta(days=1)).isoformat()
    await runtime.store.update_config("persona-a", {"quiet_delivery_windows": [{"start": "23:00", "end": "07:00"}]}, 0)
    with pytest.raises(KRDError) as error:
        await runtime.plans.apply_plan("persona-a", payload_for(day, [exact("夜间发言", "23:30", interaction="must_message"), exact("早间", "09:00")]), expected_revision=0)
    assert error.value.code == "quiet_delivery_window"
    await runtime.store.update_config("persona-a", {"blocked_execution_windows": [{"start": "01:00", "end": "03:00"}]}, 1)
    with pytest.raises(KRDError) as error:
        await runtime.plans.apply_plan("persona-a", payload_for(day, [exact("梦", "02:00", interaction="silent"), exact("早间", "09:00")]), expected_revision=0)
    assert error.value.code == "blocked_execution_window"


@pytest.mark.asyncio
async def test_required_coverage_is_checked_after_update(runtime):
    day = (datetime.now().date() + timedelta(days=1)).isoformat()
    await runtime.store.update_config("persona-a", {"required_coverage_windows": [{"start": "08:00", "end": "10:00", "min_items": 1, "max_items": 2}]}, 0)
    with pytest.raises(KRDError) as error:
        await runtime.plans.apply_plan("persona-a", payload_for(day, [exact("下午", "14:00"), exact("傍晚", "18:00")]), expected_revision=0)
    assert error.value.code == "required_coverage"
    result = await runtime.plans.apply_plan("persona-a", payload_for(day, [exact("早晨", "08:30"), exact("傍晚", "18:00")]), expected_revision=0)
    assert result["revision"] == 1


@pytest.mark.asyncio
async def test_no_immediate_repeat_returns_previous_to_next_pool(runtime):
    runtime.ctx.session_mgr.get_sessions = lambda include_content=False, kind=None: asyncio_result([
        SimpleNamespace(sid="qq:dm:1", session_title="一", adapter_name="qq"),
        SimpleNamespace(sid="qq:dm:2", session_title="二", adapter_name="qq"),
        SimpleNamespace(sid="qq:dm:3", session_title="三", adapter_name="qq"),
    ])
    await runtime.store.update_config("persona-a", {"execution_pool": {"strategy": "no_immediate_repeat", "sessions": []}}, 0)
    values = [await runtime.policy.select_session("persona-a", "execution") for _ in range(30)]
    assert all(a != b for a, b in zip(values, values[1:]))
    assert set(values) == {"qq:dm:1", "qq:dm:2", "qq:dm:3"}


@pytest.mark.asyncio
async def test_triggered_item_cannot_be_rewritten(runtime):
    day = (datetime.now().date() + timedelta(days=1)).isoformat()
    result = await runtime.plans.apply_plan("persona-a", payload_for(day, [exact("一", "08:00"), exact("二", "09:00")]), expected_revision=0)
    plan = result["plan"]
    first = plan["blocks"][0]["items"][0]
    await runtime.store.execute("UPDATE items SET state='triggered' WHERE id=?", (first["id"],))
    plan["blocks"][0]["items"][0]["title"] = "篡改历史"
    with pytest.raises(KRDError) as error:
        await runtime.plans.apply_plan("persona-a", plan, actor="user", expected_revision=1)
    assert error.value.code == "item_terminal"


def asyncio_result(value):
    async def result(): return value
    return result()
