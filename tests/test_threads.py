from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio

from krd.models import KRDError
from krd.store import dumps
from .fakes import FakeRuntime


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    yield value
    await value.close()


@pytest.mark.asyncio
async def test_thread_lifecycle_and_short_id(runtime):
    thread = await runtime.threads.add("persona-a", {
        "kind": "promise", "title": "给阿岚画头像",
        "dossier": "阿岚想要一张半身像；周五前看线稿。",
        "next_step": "起稿", "due_at": day(3), "priority": 2,
    })
    assert thread["id"].startswith("thr_")
    assert thread["short_id"] and len(thread["short_id"]) == 8
    assert thread["due_in_days"] == 3 and thread["dossier"].startswith("阿岚")

    listed = await runtime.threads.list("persona-a")
    assert [row["title"] for row in listed] == ["给阿岚画头像"]
    assert listed[0]["dossier"].endswith("…") is False

    detail = await runtime.threads.get("persona-a", thread["short_id"])
    assert detail["id"] == thread["id"] and detail["logs"] == []

    updated = await runtime.threads.update(
        "persona-a", thread["short_id"], {"dossier": "周五前看线稿；颜色可以慢慢来。"})
    assert "颜色" in updated["dossier"]

    touched = await runtime.threads.touch(
        "persona-a", thread["short_id"], "起稿完成", next_step="修线稿")
    assert touched["log"]["note"] == "起稿完成"
    detail = await runtime.threads.get("persona-a", thread["id"])
    assert detail["next_step"] == "修线稿"
    assert detail["logs"][0]["note"] == "起稿完成"

    closed = await runtime.threads.close("persona-a", thread["id"], "done", "已交付")
    assert closed["status"] == "done"
    assert (await runtime.threads.counts("persona-a"))["done"] == 1
    assert await runtime.threads.required("persona-a") == []


@pytest.mark.asyncio
async def test_thread_required_order_and_response_coverage(runtime):
    overdue = await runtime.threads.add("persona-a", {
        "kind": "promise", "title": "过期的约定", "dossier": "x", "due_at": day(-2)})
    due = await runtime.threads.add("persona-a", {
        "kind": "goal", "title": "快到期的目标", "dossier": "y", "due_at": day(1)})
    stale = await runtime.threads.add("persona-a", {
        "kind": "mystery", "title": "长期悬着", "dossier": "z"})
    await runtime.store.execute("UPDATE threads SET last_touched=? WHERE id=?",
                                (__import__("time").time() - 9 * 86400, stale["id"]))
    required = await runtime.threads.required("persona-a")
    assert [row["title"] for row in required][:3] == ["过期的约定", "快到期的目标", "长期悬着"]
    assert all(row["response_required"] for row in required)

    run_id = "prn_thread_test"
    await runtime.store.execute(
        "INSERT INTO planning_runs(id,trigger_id,persona_id,kind,target_date,session_id,status,"
        "required_thread_ids_json,response_status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, "t1", "persona-a", "daily", day(2), "qq:dm:10001", "prepared",
         dumps([overdue["id"], due["id"], stale["id"]]), "pending", "test", __import__("time").time()))
    partial = await runtime.threads.record_responses("persona-a", run_id, [
        {"thread_id": overdue["id"], "response": "advance", "note": "今天处理"},
    ])
    assert partial["status"] == "partial"
    assert len(partial["missing"]) == 2
    done = await runtime.threads.record_responses("persona-a", run_id, [
        {"thread_id": due["id"], "response": "no_change", "note": "这周先不动"},
        {"thread_id": stale["id"], "response": "no_change", "note": "还没想清楚"},
    ])
    assert done["status"] == "done"
    assert done["missing"] == []
    assert (await runtime.store.one("SELECT response_status FROM planning_runs WHERE id=?", (run_id,)))[
        "response_status"] == "done"


@pytest.mark.asyncio
async def test_thread_delete_and_restore(runtime):
    thread = await runtime.threads.add("persona-a", {"kind": "goal", "title": "可以删除"})
    await runtime.threads.delete("persona-a", thread["id"], actor="user")
    assert await runtime.threads.list("persona-a", status="open") == []
    deleted = await runtime.threads.list("persona-a", status="deleted")
    assert len(deleted) == 1
    detail = await runtime.threads.get("persona-a", thread["id"])
    assert detail["status"] == "deleted"
    restored = await runtime.threads.update("persona-a", thread["id"], {"status": "open"})
    assert restored["status"] == "open"


@pytest.mark.asyncio
async def test_thread_link_only_open_and_plan_item_persists(runtime):
    paused = await runtime.threads.add("persona-a", {"kind": "goal", "title": "暂停的线", "status": "paused"})
    with pytest.raises(KRDError) as exc:
        await runtime.plans._prepare_items("persona-a", {
            "date": day(1), "items": [{"title": "x", "at": "09:00",
                                       "target": "qq:dm:10001", "thread_id": paused["id"]}],
        }, "bot")
    assert exc.value.code == "thread_not_open"

    active = await runtime.threads.add("persona-a", {"kind": "goal", "title": "活跃线"})
    result = await runtime.plans.apply_plan("persona-a", {
        "date": day(1), "title": "测试", "items": [
            {"title": "推进", "at": "10:00", "target": "qq:dm:10001", "thread_id": active["id"]},
            {"title": "普通", "at": "11:00", "target": "qq:dm:10001"},
        ],
    }, actor="bot", mode="create", expected_revision=0)
    items = result["plan"]["blocks"][0]["items"]
    linked = next(item for item in items if item["title"] == "推进")
    assert linked["thread_id"] == active["id"]


@pytest.mark.asyncio
async def test_planning_payload_shows_top_dossiers_and_excerpts(runtime):
    for index in range(6):
        thread = await runtime.threads.add("persona-a", {
            "kind": "goal", "title": f"目标 {index}", "dossier": f"档案{index}" * 200,
            "next_step": f"下一步 {index}", "priority": max(0, 3 - index)})
        if index == 0:
            await runtime.threads.touch("persona-a", thread["id"], "第一步完成")
    payload = await runtime.threads.planning_payload("persona-a")
    assert payload["required"] is True
    assert len(payload["threads"]) == 6
    assert all(len(row["dossier"]) > 300 for row in payload["threads"][:5])
    assert len(payload["threads"][5]["dossier"]) <= 301
    assert payload["threads"][0]["logs"][0]["note"] == "第一步完成"


@pytest.mark.asyncio
async def test_chat_block_defaults_to_top_five(runtime):
    for index in range(7):
        await runtime.threads.add("persona-a", {
            "kind": "goal", "title": f"目标 {index}", "next_step": f"下一步 {index}",
            "priority": max(0, 3 - index)})
    block = await runtime.threads.chat_block("persona-a")
    lines = block.splitlines()
    assert lines[0] == "[KRD Threads]"
    assert len([line for line in lines[1:] if line.startswith("[")]) == 5
    assert lines[-1] == "(+2 more)"


@pytest.mark.asyncio
async def test_planning_payload_covers_all_required_threads(runtime):
    for index in range(12):
        await runtime.threads.add("persona-a", {"kind": "goal", "title": f"目标 {index}",
                                                "dossier": f"档案 {index}"})
    payload = await runtime.threads.planning_payload("persona-a")
    assert len(payload["threads"]) == 8
    assert payload["more"] == 4
    assert all(row["response_required"] for row in payload["threads"])

    await runtime.store.update_config(
        "persona-a", {"threads": {"planning_limit": 10, "response_limit": 8}}, 0)
    wider = await runtime.threads.planning_payload("persona-a")
    assert len(wider["threads"]) == 10
    assert sum(1 for row in wider["threads"] if row["response_required"]) == 8
    assert wider["threads"][8]["response_required"] is False


@pytest.mark.asyncio
async def test_thread_checkin_helpers(runtime):
    thread = await runtime.threads.add("persona-a", {"kind": "project", "title": "修相机"})
    await runtime.threads.auto_touch("persona-a", thread["id"], "执行了「拆底盖」", item_id="itm_test")
    assert await runtime.threads.item_was_touched(thread["id"], "itm_test", 0)
    assert not await runtime.threads.item_was_touched(thread["id"], "itm_other", 0)
    assert await runtime.threads.untouched("persona-a") == []


@pytest.mark.asyncio
async def test_due_at_supports_seconds(runtime):
    due = f"{day(2)} 18:30:45"
    thread = await runtime.threads.add("persona-a", {
        "kind": "promise", "title": "秒级约定", "dossier": "x", "due_at": due})
    assert thread["due_at"] == due and thread["due"] == due
    block = await runtime.threads.chat_block("persona-a")
    assert "18:30:45" in block
    updated = await runtime.threads.update("persona-a", thread["id"], {"due_at": f"{day(3)} 09:05:07"})
    assert updated["due_at"].endswith("09:05:07")


@pytest.mark.asyncio
async def test_closed_thread_cannot_be_checked_in(runtime):
    thread = await runtime.threads.add("persona-a", {"kind": "goal", "title": "已完成"})
    await runtime.threads.close("persona-a", thread["id"], "done", "完成")
    with pytest.raises(KRDError) as exc:
        await runtime.threads.touch("persona-a", thread["id"], "再补一句")
    assert exc.value.code == "thread_not_open"


@pytest.mark.asyncio
async def test_thread_validation(runtime):
    with pytest.raises(KRDError) as exc:
        await runtime.threads.add("persona-a", {"kind": "unknown", "title": "x"})
    assert exc.value.code == "invalid_thread_kind"
    with pytest.raises(KRDError) as exc:
        await runtime.threads.add("persona-a", {"kind": "goal", "title": "x", "due_at": "tomorrow"})
    assert exc.value.code == "invalid_due_at"
    thread = await runtime.threads.add("persona-a", {"kind": "goal", "title": "x"})
    with pytest.raises(KRDError) as exc:
        await runtime.threads.update("persona-a", thread["id"], {"priority": 9})
    assert exc.value.code == "invalid_thread_priority"
