from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
import pytest_asyncio

from .fakes import FakeRuntime, create_due_plan


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    yield value
    await value.close()


def two_sessions(runtime):
    async def sessions(include_content=False, kind=None):
        return [SimpleNamespace(sid="qq:dm:10001", session_title="执行会话", adapter_name="qq"),
                SimpleNamespace(sid="qq:dm:10002", session_title="规划会话", adapter_name="qq")]
    runtime.ctx.session_mgr.get_sessions = sessions


@pytest.mark.asyncio
async def test_all_triggered_defaults_to_planning_pool(runtime):
    two_sessions(runtime)
    await runtime.store.update_config("persona-a", {"planning_pool": {
        "sessions": ["qq:dm:10002"], "strategy": "pure_random"}}, 0)
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    await runtime.scheduler.on_response(event, SimpleNamespace(text_response="完成", tool_calls=[], status="success"))
    row = await runtime.store.one("SELECT * FROM planning_runs WHERE kind='all_triggered'")
    assert row["session_id"] == "qq:dm:10002"


@pytest.mark.asyncio
async def test_all_triggered_can_use_last_actual_response_session(runtime):
    two_sessions(runtime)
    await runtime.store.update_config("persona-a", {
        "planning_pool": {"sessions": ["qq:dm:10002"], "strategy": "pure_random"},
        "all_triggered_target_mode": "last_session",
    }, 0)
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    await runtime.scheduler.on_response(event, SimpleNamespace(text_response="完成", tool_calls=[], status="success"))
    row = await runtime.store.one("SELECT * FROM planning_runs WHERE kind='all_triggered'")
    assert row["session_id"] == "qq:dm:10001"


@pytest.mark.asyncio
async def test_review_is_disabled_by_default(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.store.execute("UPDATE items SET scheduled_at=? WHERE id=?", (time.time() + 7200, item["id"]))
    config = await runtime.store.get_config("persona-a")
    assert await runtime.scheduler._review_candidate("persona-a", config) is None


@pytest.mark.asyncio
async def test_review_targets_next_item_and_is_idempotent_without_auto_plan(runtime):
    await runtime.store.update_config("persona-a", {
        "auto_plan": False,
        "planning_review": {"enabled": True, "interval_minutes": 60, "min_lead_minutes": 30},
    }, 0)
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.store.execute("UPDATE items SET scheduled_at=? WHERE id=?", (time.time() + 7200, item["id"]))
    await runtime.store.execute("UPDATE plans SET updated_at=? WHERE id=?", (time.time() - 7200, plan["id"]))
    await runtime.scheduler.dispatch_due()
    rows = await runtime.store.all("SELECT * FROM planning_runs WHERE kind='review'")
    assert len(rows) == 1 and rows[0]["session_id"] == item["target"]
    event = runtime.ctx.event_bus.events[-1]
    metadata = runtime.context_builder.metadata(event)[0]
    assert metadata["kind"] == "review"
    prompt = await runtime.context_builder.review_prompt(metadata)
    assert "current_plan" in prompt and "next_item" in prompt and "非强制" in prompt
    await runtime.scheduler.dispatch_due()
    assert len(await runtime.store.all("SELECT * FROM planning_runs WHERE kind='review'")) == 1


@pytest.mark.asyncio
async def test_due_review_defers_in_quiet_window(runtime):
    await runtime.store.update_config("persona-a", {
        "auto_plan": False,
        "planning_review": {"enabled": True, "interval_minutes": 60, "min_lead_minutes": 30},
        "quiet_delivery_windows": [{"start": "00:00", "end": "23:59"}],
    }, 0)
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.store.execute("UPDATE items SET scheduled_at=? WHERE id=?", (time.time() + 7200, item["id"]))
    await runtime.store.execute("UPDATE plans SET updated_at=? WHERE id=?", (time.time() - 7200, plan["id"]))
    config = await runtime.store.get_config("persona-a")
    candidate = await runtime.scheduler._review_candidate("persona-a", config)
    assert candidate["due"] > time.time()
    assert await runtime.store.all("SELECT * FROM planning_runs WHERE kind='review'") == []
