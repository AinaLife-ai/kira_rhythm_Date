from __future__ import annotations

import json
import time
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio

from krd import tools
from krd.store import dumps
from .fakes import FakeRuntime


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def event(runtime, run_id="prn_ctx", kind="planning", target=None):
    return SimpleNamespace(
        _krd_runtime=runtime,
        messages=[SimpleNamespace(extra={"krd": {
            "run_id": run_id, "kind": kind, "persona_id": "persona-a",
            "date": target or day(2), "item_id": "", "plan_id": "",
        }})],
        sid="qq:dm:10001",
    )


async def add_plan(runtime, day_value, title, thread_id=""):
    payload = {"date": day_value, "title": title, "overview": "照常", "items": [
        {"title": f"{title} 小项", "at": "10:00", "intent": "测试", "instruction": "执行说明",
         "target": "qq:dm:10001", "thread_id": thread_id},
        {"title": f"{title} 收尾", "at": "20:00", "intent": "收尾", "instruction": "收尾说明",
         "target": "qq:dm:10001"},
    ]}
    return await runtime.plans.apply_plan("persona-a", payload, actor="bot", mode="create", expected_revision=0)


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    yield value
    await value.close()


@pytest.mark.asyncio
async def test_planning_context_has_detail_threads_and_outcomes(runtime):
    thread = await runtime.threads.add("persona-a", {
        "kind": "promise", "title": "给阿岚画头像", "dossier": "阿岚想要半身像；周五前看线稿。",
        "next_step": "修线稿", "due_at": day(5)})
    for offset, title in ((1, "明天"), (2, "后天"), (3, "大后天")):
        await add_plan(runtime, day(offset), title, thread["id"] if offset == 1 else "")
    prompt = await runtime.context_builder.planning_prompt({
        "persona_id": "persona-a", "kind": "planning", "date": day(4), "run_id": "x", "reason": "probe"})
    body = json.loads(prompt.split("\n", 1)[1])
    assert "previous_plans" not in body
    assert len(body["recent_plans"]["full"]) == 3
    assert "instruction" in body["recent_plans"]["full"][0]["blocks"][0]["items"][0]
    assert body["threads_requiring_response"][0]["title"] == "给阿岚画头像"
    assert "thread_response" in body["response_contract"]
    assert "recent_outcomes" in body
    assert "recent_pattern" in body
    item = next(item for plan in body["recent_plans"]["full"]
                for block in plan["blocks"] for item in block["items"] if item.get("thread_id"))
    assert item["thread_id"] == thread["id"]


@pytest.mark.asyncio
async def test_planning_context_budget_returns_valid_json(runtime):
    await runtime.threads.add("persona-a", {
        "kind": "goal", "title": "长目标", "dossier": "很长的档案" * 400, "next_step": "下一步"})
    await runtime.store.execute(
        "UPDATE settings SET value_json=json_set(value_json,'$.history_char_budget',600) WHERE key='global'")
    prompt = await runtime.context_builder.planning_prompt({
        "persona_id": "persona-a", "kind": "planning", "date": day(2), "run_id": "x"})
    body = json.loads(prompt.split("\n", 1)[1])
    assert isinstance(body, dict)


@pytest.mark.asyncio
async def test_compact_state_injects_threads_block(runtime):
    await runtime.threads.add("persona-a", {"kind": "promise", "title": "给阿岚画头像",
                                            "dossier": "档案", "next_step": "修线稿"})
    text = await runtime.context_builder.compact_state("persona-a")
    assert "[KRD Threads]" in text and "给阿岚画头像" in text


@pytest.mark.asyncio
async def test_planning_thread_response_can_be_optional(runtime):
    await runtime.threads.add("persona-a", {"kind": "goal", "title": "参考目标", "dossier": "档案"})
    await runtime.store.update_config("persona-a", {"threads": {"require_response": False}}, 0)
    prompt = await runtime.context_builder.planning_prompt({
        "persona_id": "persona-a", "kind": "planning", "date": day(2), "run_id": "x"})
    body = json.loads(prompt.split("\n", 1)[1])
    assert "threads_requiring_response" not in body
    assert body["threads_reference"][0]["title"] == "参考目标"
    assert body["threads_reference"][0]["response_required"] is False
    assert "response_contract" not in body


@pytest.mark.asyncio
async def test_chat_block_default_on_and_can_be_disabled(runtime):
    await runtime.threads.add("persona-a", {"kind": "promise", "title": "给阿岚画头像",
                                            "dossier": "档案全文", "next_step": "修线稿"})
    block = await runtime.threads.chat_block("persona-a")
    assert block.startswith("[KRD Threads]") and "档案全文" not in block
    config = await runtime.store.get_config("persona-a")
    config["threads"]["chat_enabled"] = False
    assert await runtime.threads.chat_block("persona-a", config) == ""


@pytest.mark.asyncio
async def test_item_prompt_has_day_so_far_and_linked_thread(runtime):
    thread = await runtime.threads.add("persona-a", {"kind": "project", "title": "修相机",
                                                     "dossier": "快门有点涩", "next_step": "拆底盖"})
    result = await add_plan(runtime, day(2), "今天", thread["id"])
    item = next(item for item in result["plan"]["blocks"][0]["items"] if item["title"].endswith("小项"))
    await runtime.store.execute("UPDATE items SET state='triggered_silent' WHERE plan_id=? AND id<>?",
                                (result["plan"]["id"], item["id"]))
    prompt = await runtime.context_builder.item_prompt({
        "persona_id": "persona-a", "kind": "item", "item_id": item["id"], "run_id": "x"})
    body = json.loads(prompt.split("\n", 1)[1])
    assert body["thread"]["title"] == "修相机"
    assert body["day_so_far"]["done"]


@pytest.mark.asyncio
async def test_planning_requires_thread_response_and_accepts_no_change(runtime):
    thread = await runtime.threads.add("persona-a", {"kind": "goal", "title": "学做三道菜",
                                                     "dossier": "档案", "next_step": "找菜谱"})
    run_id = "prn_response"
    await runtime.store.execute(
        "INSERT INTO planning_runs(id,trigger_id,persona_id,kind,target_date,session_id,status,"
        "required_thread_ids_json,response_status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, "t", "persona-a", "daily", day(2), "qq:dm:10001", "prepared",
         dumps([thread["id"]]), "pending", "test", time.time()))
    ev = event(runtime, run_id)
    payload = {"date": day(2), "title": "测试", "items": [
        {"title": "A", "at": "09:00", "target": "qq:dm:10001"},
        {"title": "B", "at": "10:00", "target": "qq:dm:10001"},
    ]}
    rejected = json.loads(await tools.rhythm_plan(ev, plans=[payload]))
    assert rejected["error"]["code"] == "thread_response_required"
    response = json.loads(await tools.rhythm_update(ev, operations=[
        {"type": "thread_response", "thread_id": thread["id"],
         "response": "no_change", "note": "这周先不动，周末再看"},
    ]))
    assert response["ok"] and response["results"][0]["result"]["status"] == "done"
    accepted = json.loads(await tools.rhythm_plan(ev, plans=[payload]))
    assert accepted["ok"] and accepted["days"][0]["revision"] == 1
    row = await runtime.store.one("SELECT status,response_status FROM planning_runs WHERE id=?", (run_id,))
    assert row["status"] == "completed" and row["response_status"] == "done"


@pytest.mark.asyncio
async def test_thread_close_counts_as_implicit_response(runtime):
    thread = await runtime.threads.add("persona-a", {"kind": "promise", "title": "要完成的约定"})
    run_id = "prn_close"
    await runtime.store.execute(
        "INSERT INTO planning_runs(id,trigger_id,persona_id,kind,target_date,session_id,status,"
        "required_thread_ids_json,response_status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, "t2", "persona-a", "daily", day(2), "qq:dm:10001", "prepared",
         dumps([thread["id"]]), "pending", "test", time.time()))
    ev = event(runtime, run_id)
    closed = json.loads(await tools.rhythm_update(ev, operations=[
        {"type": "thread_close", "thread_id": thread["id"], "status": "done", "note": "提前完成"},
    ]))
    assert closed["ok"]
    accepted = json.loads(await tools.rhythm_plan(ev, plans=[{
        "date": day(2), "title": "测试", "items": [
            {"title": "A", "at": "09:00", "target": "qq:dm:10001"},
            {"title": "B", "at": "10:00", "target": "qq:dm:10001"},
        ]}]))
    assert accepted["ok"]
