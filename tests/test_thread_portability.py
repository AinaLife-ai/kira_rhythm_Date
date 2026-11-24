from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio

from krd import webapi
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
async def test_thread_and_item_link_survive_export_import(runtime):
    thread = await runtime.threads.add("persona-a", {
        "kind": "promise", "title": "给阿岚画头像", "dossier": "周五前看线稿。",
        "next_step": "修线稿", "due_at": day(3)})
    await runtime.threads.touch("persona-a", thread["id"], "起稿完成", next_step="修线稿")
    await runtime.plans.apply_plan("persona-a", {
        "date": day(1), "title": "测试", "items": [
            {"title": "修线稿", "at": "10:00", "target": "qq:dm:10001", "thread_id": thread["id"]},
            {"title": "群答疑", "at": "11:00", "target": "qq:dm:10001"},
        ],
    }, actor="bot", mode="create", expected_revision=0)

    data = await webapi.export_data(runtime, "persona-a")
    assert data["schema_version"] == 2
    assert len(data["tables"]["threads"]) == 1
    assert len(data["tables"]["thread_logs"]) == 1
    preview = await webapi.import_preview(runtime, "persona-b", data)
    assert preview["threads"] == 1
    result = await webapi.import_commit(runtime, "persona-b", data)
    assert result["imported_threads"] == 1

    threads = await runtime.threads.list("persona-b")
    assert [row["title"] for row in threads] == ["给阿岚画头像"]
    imported_thread = threads[0]
    detail = await runtime.threads.get("persona-b", imported_thread["id"])
    assert detail["logs"][0]["note"] == "起稿完成"

    plan = await runtime.plans.get_plan_by_date("persona-b", day(1))
    linked = next(item for item in plan["blocks"][0]["items"] if item["title"] == "修线稿")
    assert linked["thread_id"] == imported_thread["id"]
