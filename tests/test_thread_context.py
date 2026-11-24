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

@pytest.mark.asyncio
async def test_planning_context_uses_persisted_run_required_ids(runtime):
    for index in range(3):
        await runtime.threads.add("persona-a", {
            "kind": "goal", "title": f"既有目标 {index}", "dossier": f"档案 {index}",
            "priority": 3 - index, "due_at": day(index + 1)})
    await runtime.store.update_config(
        "persona-a", {"threads": {"planning_limit": 3, "response_limit": 2}}, 0)
    run = await runtime.scheduler.trigger_planning("persona-a", "manual", day(2), "race probe")
    required_ids = json.loads(run["required_thread_ids_json"])
    assert len(required_ids) == 2
    # A thread created after the trigger must not silently become required for
    # this already-dispatched run.
    late = await runtime.threads.add("persona-a", {
        "kind": "promise", "title": "触发后新增", "dossier": "晚到", "priority": 3,
        "due_at": day(0)})
    prompt = await runtime.context_builder.planning_prompt({
        "persona_id": "persona-a", "kind": "planning", "date": day(2), "run_id": run["id"]})
    body = json.loads(prompt.split("\n", 1)[1])
    visible = body["threads_requiring_response"]
    assert {row["id"] for row in visible} == set(required_ids)
    assert all(row["response_required"] is True for row in visible)
    assert late["id"] not in required_ids
    assert late["id"] in {row["id"] for row in body.get("threads_reference", [])}
    assert body["response_contract"]


@pytest.mark.asyncio
async def test_planning_budget_never_drops_required_threads(runtime):
    for index in range(8):
        await runtime.threads.add("persona-a", {
            "kind": "goal", "title": f"必须回应 {index}", "dossier": "很长的档案" * 100,
            "next_step": "下一步" * 50})
    await runtime.store.execute(
        "UPDATE settings SET value_json=json_set(value_json,'$.history_char_budget',500) WHERE key='global'")
    prompt = await runtime.context_builder.planning_prompt({
        "persona_id": "persona-a", "kind": "planning", "date": day(2), "run_id": "missing-run"})
    body = json.loads(prompt.split("\n", 1)[1])
    required = body["threads_requiring_response"]
    assert len(required) == 8
    assert all(row.get("response_required") is True for row in required)
    assert body["response_contract"]


@pytest.mark.asyncio
async def test_optional_reference_has_clear_no_response_instruction(runtime):
    await runtime.threads.add("persona-a", {"kind": "goal", "title": "可选目标", "dossier": "档案"})
    await runtime.store.update_config("persona-a", {"threads": {"require_response": False}}, 0)
    prompt = await runtime.context_builder.planning_prompt({
        "persona_id": "persona-a", "kind": "planning", "date": day(2), "run_id": "missing-run"})
    body = json.loads(prompt.split("\n", 1)[1])
    assert "threads_requiring_response" not in body
    assert body["threads_reference"][0]["response_required"] is False
    assert "没有必须回应的目标" in body["instruction"]

@pytest.mark.asyncio
async def test_disabled_thread_layer_rejects_model_writes(runtime):
    event = SimpleNamespace(_krd_runtime=runtime, messages=[], sid="qq:dm:10001")
    await runtime.store.update_config("persona-a", {"threads": {"enabled": False}}, 0)
    result = json.loads(await tools.rhythm_update(event, operations=[
        {"type": "thread_add", "kind": "goal", "title": "不该写入", "dossier": "档案"},
    ]))
    assert result["error"]["code"] == "threads_disabled"


@pytest.mark.asyncio
async def test_persisted_requirement_survives_config_toggle(runtime):
    thread = await runtime.threads.add("persona-a", {"kind": "goal", "title": "必须回应"})
    run_id = "prn_toggle"
    await runtime.store.execute(
        "INSERT INTO planning_runs(id,trigger_id,persona_id,kind,target_date,session_id,status,"
        "required_thread_ids_json,response_status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, "toggle", "persona-a", "daily", day(2), "qq:dm:10001", "prepared",
         dumps([thread["id"]]), "pending", "test", time.time()))
    await runtime.store.update_config("persona-a", {"threads": {"require_response": False}}, 0)
    ev = event(runtime, run_id)
    result = json.loads(await tools.rhythm_plan(ev, plans=[{
        "date": day(2), "title": "测试", "items": [
            {"title": "A", "at": "09:00", "target": "qq:dm:10001"},
            {"title": "B", "at": "10:00", "target": "qq:dm:10001"},
        ]}]))
    assert result["error"]["code"] == "thread_response_required"

def test_item_budget_keeps_current_item_actionable():
    from krd.context import ContextBuilder
    payload = {
        "instruction": "执行说明" * 1000,
        "current_item": {"id": "itm_keep", "title": "现在要做的事", "instruction": "执行说明"},
        "delivery_policy": {"effective_interaction": "auto"},
        "recent_diff": [{"revision": index, "diff": [{"op": "changed", "title": "x" * 100}]} for index in range(20)],
        "siblings": [{"id": f"itm_{index}", "title": "参考" * 40} for index in range(100)],
        "thread": {"id": "thr_keep", "title": "关联目标", "dossier": "档案" * 1000, "logs": [{"note": "很长的打卡" * 100}]},
    }
    body = json.loads(ContextBuilder._fit_payload(payload, 500))
    assert body["current_item"]["id"] == "itm_keep"
    assert body["delivery_policy"]["effective_interaction"] == "auto"

@pytest.mark.asyncio
async def test_closed_thread_link_does_not_block_plan_revision(runtime):
    import copy
    thread = await runtime.threads.add("persona-a", {"kind": "goal", "title": "已完成目标"})
    result = await add_plan(runtime, day(2), "原计划", thread["id"])
    await runtime.threads.close("persona-a", thread["id"], "done", "已完成")
    payload = copy.deepcopy(result["plan"])
    payload["title"] = "修订后的计划"
    revised = await runtime.plans.apply_plan(
        "persona-a", payload, actor="user", mode="revise", expected_revision=result["plan"]["revision"])
    assert revised["plan"]["title"] == "修订后的计划"
    linked = [item for block in revised["plan"]["blocks"] for item in block["items"] if item.get("thread_id")]
    assert linked and linked[0]["thread_id"] == thread["id"]

@pytest.mark.asyncio
async def test_disabled_thread_layer_removes_contract_from_planning(runtime):
    await runtime.threads.add("persona-a", {"kind": "goal", "title": "关闭后不应出现"})
    await runtime.store.update_config("persona-a", {"threads": {"enabled": False}}, 0)
    prompt = await runtime.context_builder.planning_prompt({
        "persona_id": "persona-a", "kind": "planning", "date": day(2), "run_id": "missing-run"})
    body = json.loads(prompt.split("\n", 1)[1])
    assert "threads_requiring_response" not in body
    assert "threads_reference" not in body
    assert "未启用目标/约定" in body["instruction"]

@pytest.mark.asyncio
async def test_planning_does_not_force_reply_to_user_metadata(runtime):
    prompt = await runtime.context_builder.planning_prompt({
        "persona_id": "persona-a", "kind": "planning", "date": day(2), "run_id": "missing-run",
        "has_real_user": True})
    body = json.loads(prompt.split("\n", 1)[1])
    assert "必须先正常回答用户" not in body["instruction"]
    assert "必须正常回答用户" not in body["instruction"]

@pytest.mark.asyncio
async def test_finished_thread_stays_as_history_in_item_prompt(runtime):
    thread = await runtime.threads.add("persona-a", {
        "kind": "goal", "title": "已经完成的目标", "dossier": "完成后仍可回看"})
    result = await add_plan(runtime, day(2), "今天", thread["id"])
    item = next(item for item in result["plan"]["blocks"][0]["items"] if item["title"].endswith("小项"))
    await runtime.threads.close("persona-a", thread["id"], "done", "完成")
    prompt = await runtime.context_builder.item_prompt({
        "persona_id": "persona-a", "kind": "item", "item_id": item["id"], "run_id": "x"})
    body = json.loads(prompt.split("\n", 1)[1])
    assert body["thread"]["status"] == "done"
    assert "已完成" in body["thread"]["dossier"] or body["thread"]["dossier"]
    assert "目标已结束" in body["instruction"]
    assert "不要用 thread_touch" in body["instruction"]
