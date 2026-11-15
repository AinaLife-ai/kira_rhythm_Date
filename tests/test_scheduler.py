from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
import pytest_asyncio

from krd.context import ContextBuilder
from .fakes import FakeRuntime, create_due_plan


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    yield value
    await value.close()


def metadata_event(runtime, plan, run):
    event = runtime.ctx.event_bus.events[-1]
    assert ContextBuilder.metadata(event)[0]["run_id"] == run["id"]
    return event


@pytest.mark.asyncio
async def test_claim_publish_is_idempotent(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    assert run and run["status"] == "prepared"
    assert await runtime.scheduler.claim_item(item["id"]) is None
    event = metadata_event(runtime, plan, run)
    assert event.messages[0].is_notice
    assert event.messages[0].extra["krd"]["item_id"] == item["id"]
    assert event.messages[0].sender.user_id == "system_krd"
    row = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert row["state"] == "queued"


@pytest.mark.asyncio
async def test_empty_msg_is_triggered_silent(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    event = metadata_event(runtime, plan, run)
    response = SimpleNamespace(text_response="<msg/>", tool_calls=[], status="success", input_tokens=3, output_tokens=1)
    await runtime.scheduler.on_response(event, response)
    row = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert row["state"] == "triggered_silent"
    receipt = await runtime.store.one("SELECT status,input_tokens FROM runs WHERE id=?", (run["id"],))
    assert receipt["status"] == "responded" and receipt["input_tokens"] == 3


@pytest.mark.asyncio
async def test_probability_skip_never_rerolls(runtime):
    plan = await create_due_plan(runtime, probability=0, count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    assert run["status"] == "skipped_probability" and run["draw"] >= 0
    assert not [event for event in runtime.ctx.event_bus.events
                if any(item.get("kind") == "item" for item in ContextBuilder.metadata(event))]
    assert await runtime.scheduler.claim_item(item["id"]) is None
    row = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert row["state"] == "skipped_probability"


@pytest.mark.asyncio
async def test_expired_item_is_missed_not_user_busy(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.store.execute("UPDATE items SET scheduled_at=? WHERE id=?", (time.time() - 1000, item["id"]))
    run = await runtime.scheduler.claim_item(item["id"])
    assert run is None
    row = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert row["state"] == "missed"


@pytest.mark.asyncio
async def test_persona_switch_does_not_close_old_persona_run(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    event = metadata_event(runtime, plan, run)
    runtime.ctx.persona_mgr.active = "persona-b"
    await runtime.scheduler.on_response(event, SimpleNamespace(text_response="你好", tool_calls=[], status="success"))
    row = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert row["state"] == "queued"


@pytest.mark.asyncio
async def test_recovery_marks_ambiguous_run_interrupted(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    await runtime.scheduler.recover()
    receipt = await runtime.store.one("SELECT status FROM runs WHERE id=?", (run["id"],))
    assert receipt["status"] == "interrupted"
