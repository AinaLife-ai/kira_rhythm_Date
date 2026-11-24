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

@pytest.mark.asyncio
async def test_must_message_with_silent_text_and_tool_call_is_delivery_unmet(runtime):
    plan = await create_due_plan(runtime, interaction="must_message", count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    event = metadata_event(runtime, plan, run)
    response = SimpleNamespace(text_response="<msg/>", tool_calls=[{}], status="success")
    await runtime.scheduler.on_response(event, response)
    receipt = await runtime.store.one("SELECT error FROM runs WHERE id=?", (run["id"],))
    stored = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert receipt["error"] == "delivery_unmet"
    assert stored["state"] == "triggered"


@pytest.mark.asyncio
async def test_force_touch_is_enforced_even_when_auto_touch_is_enabled(runtime, monkeypatch):
    thread = await runtime.threads.add("persona-a", {"kind": "goal", "title": "关联目标"})
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.store.execute("UPDATE items SET thread_id=? WHERE id=?", (thread["id"], item["id"]))
    await runtime.store.update_config(
        "persona-a", {"threads": {"force_touch": True, "auto_touch": True}}, 0)
    run = await runtime.scheduler.claim_item(item["id"])
    event = metadata_event(runtime, plan, run)

    async def no_touch(*args, **kwargs):
        return None

    monkeypatch.setattr(runtime.threads, "auto_touch", no_touch)
    await runtime.scheduler.on_response(
        event, SimpleNamespace(text_response="做了一点", tool_calls=[], status="success"))
    await runtime.scheduler.on_final(event)
    receipt = await runtime.store.one("SELECT error FROM runs WHERE id=?", (run["id"],))
    assert "thread_untouched" in (receipt["error"] or "")

@pytest.mark.asyncio
async def test_finalize_does_not_touch_old_persona_run(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    event = metadata_event(runtime, plan, run)
    await runtime.store.execute(
        "UPDATE runs SET status='responded',responded_at=? WHERE id=?", (time.time(), run["id"]))
    runtime.ctx.persona_mgr.active = "persona-b"
    await runtime.scheduler.on_final(event)
    row = await runtime.store.one("SELECT status FROM runs WHERE id=?", (run["id"],))
    assert row["status"] == "responded"
