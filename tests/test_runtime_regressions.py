from __future__ import annotations

import asyncio
import copy
import json
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from datetime import date, time as dt_time
from unittest.mock import patch

import pytest
import pytest_asyncio

from krd.models import KRDError
from krd.tools import rhythm_update
from .fakes import FakeRuntime, create_due_plan


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    yield value
    await value.close()


def tomorrow():
    return (datetime.now().date() + timedelta(days=1)).isoformat()


def one_item_payload(schedule=None):
    return {"date": tomorrow(), "title": "回归", "blocks": [{"title": "组", "items": [{
        "title": "小项", "schedule": schedule or {"type": "exact", "at": "09:00"},
        "target": "qq:dm:10001", "interaction": "auto",
    }]}]}


@pytest.mark.asyncio
async def test_revision_preserves_window_draw_and_allows_elapsed_time(runtime):
    result = await runtime.plans.apply_plan("persona-a", one_item_payload(
        {"type": "window", "start": "08:00", "end": "10:00"}), actor="user", expected_revision=0)
    original = result["plan"]["blocks"][0]["items"][0]
    elapsed = time.time() - 3600
    await runtime.store.execute("UPDATE items SET scheduled_at=? WHERE id=?", (elapsed, original["id"]))
    plan = await runtime.plans.get_plan(result["plan"]["id"], "persona-a")
    revised = await runtime.plans.apply_plan("persona-a", plan, actor="user", expected_revision=1)
    item = revised["plan"]["blocks"][0]["items"][0]
    assert item["scheduled_at"] == elapsed
    assert item["series_id"] == original["series_id"]
    assert revised["diff"] == []


@pytest.mark.asyncio
async def test_past_exact_schedule_is_rejected_without_blocking(runtime):
    day = date.today().isoformat()
    with patch("krd.plans.now", return_value=datetime.combine(date.today(), dt_time(12)).timestamp()):
        with pytest.raises(KRDError) as error:
            await asyncio.wait_for(runtime.plans.apply_plan(
                "persona-a", {"date": day, "blocks": [{"title": "B", "items": [{
                    "title": "过期项", "schedule": {"type": "exact", "at": "09:00"},
                    "target": "qq:dm:10001"}]}]},
                actor="user", expected_revision=0,
            ), 2)
    assert error.value.code == "schedule_in_past"


@pytest.mark.asyncio
async def test_hash_prefixed_short_item_id_is_accepted(runtime):
    result = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    item = result["plan"]["blocks"][0]["items"][0]
    short = "#" + item["id"].split("_", 1)[1][:8]
    assert await runtime.plans.resolve_item_id("persona-a", short) == item["id"]


@pytest.mark.asyncio
async def test_terminal_item_can_be_retained_but_not_forged(runtime):
    result = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    plan = result["plan"]
    item = plan["blocks"][0]["items"][0]
    await runtime.store.execute("UPDATE items SET state='triggered' WHERE id=?", (item["id"],))
    plan = await runtime.plans.get_plan(plan["id"], "persona-a")
    retained = await runtime.plans.apply_plan("persona-a", plan, actor="user", expected_revision=1)
    assert retained["plan"]["blocks"][0]["items"][0]["state"] == "triggered"
    retained["plan"]["blocks"][0]["items"][0]["state"] = "scheduled"
    with pytest.raises(KRDError) as error:
        await runtime.plans.apply_plan("persona-a", retained["plan"], actor="user", expected_revision=2)
    assert error.value.code == "item_terminal"


@pytest.mark.asyncio
async def test_new_item_cannot_forge_execution_state(runtime):
    payload = one_item_payload()
    payload["blocks"][0]["items"][0]["state"] = "running"
    with pytest.raises(KRDError) as error:
        await runtime.plans.apply_plan("persona-a", payload, actor="user", expected_revision=0)
    assert error.value.code == "invalid_item_state"


@pytest.mark.asyncio
async def test_duplicate_block_ids_are_rejected_atomically(runtime):
    payload = one_item_payload()
    payload["blocks"].append(copy.deepcopy(payload["blocks"][0]))
    payload["blocks"][0]["id"] = "blk_same"
    payload["blocks"][1]["id"] = "blk_same"
    payload["blocks"][1]["items"][0]["id"] = "itm_other"
    with pytest.raises(KRDError) as error:
        await runtime.plans.apply_plan("persona-a", payload, actor="user", expected_revision=0)
    assert error.value.code == "duplicate_block_id"
    assert await runtime.plans.get_plan_by_date("persona-a", tomorrow()) is None


@pytest.mark.asyncio
async def test_create_missing_is_a_true_noop(runtime):
    first = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    second = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", mode="create_missing", expected_revision=1)
    assert second["plan"]["id"] == first["plan"]["id"]
    assert second["revision"] == 1 and second["diff"] == []


@pytest.mark.asyncio
async def test_plan_commit_wakes_scheduler(runtime):
    runtime.scheduler.wake_event.clear()
    await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    assert runtime.scheduler.wake_event.is_set()


@pytest.mark.asyncio
async def test_rhythm_update_is_atomic_and_does_not_await_sync_wake(runtime):
    event = SimpleNamespace(_krd_runtime=runtime)
    raw = await rhythm_update(event, [{"type": "day_state", "patch": {"current_mood": "平静"}}])
    assert json.loads(raw)["ok"] is True
    state = await runtime.plans.day_state("persona-a", await runtime.plans.current_date("persona-a"))
    assert state["current_mood"] == "平静"
    raw = await rhythm_update(event, [
        {"type": "day_state", "patch": {"current_mood": "不应提交"}},
        {"type": "unknown"},
    ])
    assert json.loads(raw)["error"]["code"] == "invalid_operation"
    state = await runtime.plans.day_state("persona-a", await runtime.plans.current_date("persona-a"))
    assert state["current_mood"] == "平静"


@pytest.mark.asyncio
async def test_expired_last_item_still_opens_planning_opportunity(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.store.execute("UPDATE items SET scheduled_at=? WHERE id=?", (time.time() - 1000, item["id"]))
    assert await runtime.scheduler.claim_item(item["id"]) is None
    rows = await runtime.store.all("SELECT * FROM planning_runs WHERE kind='all_triggered'")
    assert len(rows) == 1
    assert runtime.context_builder.metadata(runtime.ctx.event_bus.events[-1])[0]["kind"] == "planning"


@pytest.mark.asyncio
async def test_duplicate_response_does_not_create_extra_planning_run(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    response = SimpleNamespace(text_response="你好", tool_calls=[], status="success")
    await runtime.scheduler.on_response(event, response)
    await runtime.scheduler.on_response(event, response)
    rows = await runtime.store.all("SELECT * FROM planning_runs WHERE kind='all_triggered'")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_mixed_persona_batch_only_advances_active_run(runtime):
    timestamp = time.time()
    for identifier, persona in (("prn_a", "persona-a"), ("prn_b", "persona-b")):
        await runtime.store.execute(
            "INSERT INTO planning_runs(id,trigger_id,persona_id,kind,target_date,session_id,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (identifier, identifier, persona, "manual", tomorrow(), "qq:dm:10001", "queued", timestamp))
    await runtime.scheduler.trigger_planning("persona-a", "manual", tomorrow(), "test")
    event = runtime.ctx.event_bus.events[-1]
    # Replace the published marker with two persisted planning run markers.
    event.messages[0].extra["krd"].update({"run_id": "prn_a", "kind": "planning"})
    other = copy.deepcopy(event.messages[0])
    other.extra["krd"].update({"run_id": "prn_b", "persona_id": "persona-b"})
    event.messages.append(other)
    await runtime.scheduler.on_request(event)
    assert (await runtime.store.one("SELECT status FROM planning_runs WHERE id='prn_a'"))["status"] == "running"
    assert (await runtime.store.one("SELECT status FROM planning_runs WHERE id='prn_b'"))["status"] == "queued"


@pytest.mark.asyncio
async def test_planning_trigger_id_is_atomic_under_concurrency(runtime):
    results = await asyncio.gather(*[
        runtime.scheduler.trigger_planning("persona-a", "daily", tomorrow(), "test", "daily:race")
        for _ in range(12)
    ])
    assert len({row["id"] for row in results}) == 1
    assert len(runtime.ctx.event_bus.events) == 1


@pytest.mark.asyncio
async def test_plan_reads_have_constant_query_count(runtime):
    plan = await create_due_plan(runtime, count=3)
    counts = {"one": 0, "all": 0}
    original_one, original_all = runtime.store.one, runtime.store.all
    async def one(*args, **kwargs):
        counts["one"] += 1
        return await original_one(*args, **kwargs)
    async def all_(*args, **kwargs):
        counts["all"] += 1
        return await original_all(*args, **kwargs)
    runtime.store.one, runtime.store.all = one, all_
    await runtime.plans.get_plan(plan["id"], "persona-a")
    assert counts == {"one": 1, "all": 2}
    counts = {"one": 0, "all": 0}
    await runtime.plans.list_plans("persona-a", plan["date"], plan["date"])
    assert counts == {"one": 0, "all": 3}


@pytest.mark.asyncio
async def test_run_now_uses_plan_ownership_and_rejects_inactive_persona(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.run_now("persona-a", item["id"])
    assert run["status"] == "prepared" and run["persona_id"] == "persona-a"
    runtime.ctx.persona_mgr.active = "persona-b"
    with pytest.raises(KRDError) as error:
        await runtime.scheduler.run_now("persona-a", item["id"])
    assert error.value.code == "persona_not_active"


@pytest.mark.asyncio
async def test_concurrent_same_revision_has_one_typed_winner(runtime):
    created = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    left, right = copy.deepcopy(created["plan"]), copy.deepcopy(created["plan"])
    left["title"], right["title"] = "左侧", "右侧"
    results = await asyncio.gather(
        runtime.plans.apply_plan("persona-a", left, actor="user", expected_revision=1),
        runtime.plans.apply_plan("persona-a", right, actor="user", expected_revision=1),
        return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    failure = next(result for result in results if isinstance(result, Exception))
    assert isinstance(failure, KRDError)
    assert failure.code == "revision_conflict"
    stored = await runtime.plans.get_plan(created["plan"]["id"], "persona-a")
    assert stored["revision"] == 2


@pytest.mark.asyncio
async def test_concurrent_create_same_day_has_one_typed_winner(runtime):
    results = await asyncio.gather(*[
        runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
        for _ in range(6)
    ], return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert all(isinstance(result, KRDError) and result.code == "revision_conflict"
               for result in results if isinstance(result, Exception))
    plans = await runtime.plans.list_plans("persona-a", tomorrow(), tomorrow())
    assert len(plans) == 1 and plans[0]["revision"] == 1


@pytest.mark.asyncio
async def test_optional_startup_plan_uses_planning_metadata(runtime):
    await runtime.store.update_config("persona-a", {"startup_plan": True}, 0)
    await runtime.scheduler.start()
    try:
        assert len(runtime.ctx.event_bus.events) == 1
        metadata = runtime.context_builder.metadata(runtime.ctx.event_bus.events[0])[0]
        assert metadata["kind"] == "planning"
        assert metadata["date"] == await runtime.plans.current_date("persona-a")
    finally:
        await runtime.scheduler.stop()


@pytest.mark.asyncio
async def test_watchdog_closes_stopped_workflow_without_duplicate_dispatch(runtime):
    runtime.scheduler.watchdog_seconds = 0.02
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    await asyncio.sleep(0.06)
    receipt = await runtime.store.one("SELECT status,error FROM runs WHERE id=?", (run["id"],))
    stored = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert receipt["status"] == "interrupted" and "watchdog" in receipt["error"]
    assert stored["state"] == "interrupted"
    assert len(runtime.ctx.event_bus.events) == 1


@pytest.mark.asyncio
async def test_offline_dispatch_returns_failure_and_broadcasts_failed_state(runtime):
    plan = await create_due_plan(runtime, count=1)
    item = plan["blocks"][0]["items"][0]
    runtime.ctx.adapter_mgr.adapter.is_running = False
    with pytest.raises(KRDError) as error:
        await runtime.scheduler.run_now("persona-a", item["id"])
    assert error.value.code == "dispatch_failed"
    stored = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert stored["state"] == "failed"
    assert runtime.notices[-1] == ("item_changed", {"item_id": item["id"], "state": "failed"})

@pytest.mark.asyncio
async def test_plan_revision_accepts_current_revision_alias(runtime):
    first = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    payload = copy.deepcopy(first["plan"])
    payload["revision"] = first["revision"]
    payload["title"] = "通过 revision 别名修订"
    revised = await runtime.plans.apply_many("persona-a", [payload], actor="user", mode="revise")
    assert revised[0]["plan"]["title"] == "通过 revision 别名修订"
    assert revised[0]["revision"] == first["revision"] + 1


@pytest.mark.asyncio
async def test_plan_revision_conflict_hint_names_expected_revision(runtime):
    first = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    payload = copy.deepcopy(first["plan"])
    payload["expected_revision"] = 0
    with pytest.raises(KRDError) as error:
        await runtime.plans.apply_many("persona-a", [payload], actor="bot", mode="revise")
    assert error.value.code == "revision_conflict"
    assert "expected_revision" in error.value.details.get("hint", "")

@pytest.mark.asyncio
async def test_append_item_accepts_date_block_and_flat_fields(runtime):
    day = tomorrow()
    await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    event = SimpleNamespace(_krd_runtime=runtime, messages=[])
    result = json.loads(await rhythm_update(event, operations=[{
        "type": "append_item", "date": day, "block": "上午",
        "title": "热身", "intent": "先动起来", "instruction": "伸伸胳膊",
        "at": "11:00", "target": "qq:dm:10001", "interaction": "auto",
    }]))
    assert result["ok"], result
    plan = result["results"][0]["result"]["plan"]
    block = next(block for block in plan["blocks"] if block["title"] == "上午")
    item = next(item for item in block["items"] if item["title"] == "热身")
    assert item["schedule"]["type"] == "exact" and item["schedule"]["at"] == "11:00"


@pytest.mark.asyncio
async def test_append_item_without_plan_or_date_is_typed_error(runtime):
    event = SimpleNamespace(_krd_runtime=runtime, messages=[])
    result = json.loads(await rhythm_update(event, operations=[{
        "type": "append_item", "block": "上午", "title": "没有计划",
    }]))
    assert result["error"]["code"] == "plan_required"

@pytest.mark.asyncio
async def test_append_item_accepts_plan_id_block_and_flat_schedule(runtime):
    first = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    event = SimpleNamespace(_krd_runtime=runtime, messages=[])
    result = json.loads(await rhythm_update(event, operations=[{
        "type": "append_item", "plan_id": first["plan"]["id"], "block": "上午",
        "title": "听会儿雨", "intent": "留白", "instruction": "听雨",
        "schedule": {"type": "window", "start": "11:10", "end": "12:20", "window_mode": "single_random"},
        "target": "qq:dm:10001", "interaction": "silent", "execution_probability": 0.5,
    }]))
    assert result["ok"], result
    plan = result["results"][0]["result"]["plan"]
    block = next(block for block in plan["blocks"] if block["title"] == "上午")
    item = next(item for item in block["items"] if item["title"] == "听会儿雨")
    assert item["schedule"]["type"] == "window" and item["schedule"]["start"] == "11:10"


@pytest.mark.asyncio
async def test_update_item_accepts_flat_time_and_probability(runtime):
    payload = one_item_payload()
    payload["blocks"][0]["items"].append({
        "title": "第二项", "schedule": {"type": "exact", "at": "10:00"},
        "target": "qq:dm:10001", "interaction": "auto",
    })
    first = await runtime.plans.apply_plan("persona-a", payload, actor="user", expected_revision=0)
    item = first["plan"]["blocks"][0]["items"][0]
    event = SimpleNamespace(_krd_runtime=runtime, messages=[])
    result = json.loads(await rhythm_update(event, operations=[{
        "type": "update_item", "item_id": item["id"],
        "at": "12:15", "probability": 0.4,
    }]))
    assert result["ok"], result
    changed = result["results"][0]["result"]["plan"]["blocks"][0]["items"][0]
    assert changed["schedule"] == {"type": "exact", "at": "12:15"}
    assert changed["execution_probability"] == 0.4


@pytest.mark.asyncio
async def test_update_item_without_id_is_typed_error(runtime):
    event = SimpleNamespace(_krd_runtime=runtime, messages=[])
    result = json.loads(await rhythm_update(event, operations=[{
        "type": "update_item", "title": "缺 id",
    }]))
    assert result["error"]["code"] == "item_required"


@pytest.mark.asyncio
async def test_update_item_non_object_patch_is_typed_error(runtime):
    first = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    item = first["plan"]["blocks"][0]["items"][0]
    event = SimpleNamespace(_krd_runtime=runtime, messages=[])
    result = json.loads(await rhythm_update(event, operations=[{
        "type": "update_item", "item_id": item["id"], "patch": ["bad"],
    }]))
    assert result["error"]["code"] == "invalid_patch"

@pytest.mark.asyncio
async def test_append_item_without_time_is_typed_error(runtime):
    first = await runtime.plans.apply_plan("persona-a", one_item_payload(), actor="user", expected_revision=0)
    event = SimpleNamespace(_krd_runtime=runtime, messages=[])
    result = json.loads(await rhythm_update(event, operations=[{
        "type": "append_item", "plan_id": first["plan"]["id"], "block": "上午", "title": "没有时间",
    }]))
    assert result["error"]["code"] == "invalid_time"

@pytest.mark.asyncio
async def test_rhythm_plan_rejects_non_object_plan_without_internal_error(runtime):
    from krd.tools import rhythm_plan
    event = SimpleNamespace(_krd_runtime=runtime, messages=[])
    result = json.loads(await rhythm_plan(event, plans=["bad"]))
    assert result["error"]["code"] == "invalid_plan"
