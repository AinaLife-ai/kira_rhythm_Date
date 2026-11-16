from __future__ import annotations

import pytest

from krd.models import KRDError
from tests.fakes import FakeRuntime


async def make_plan(runtime: FakeRuntime, day: str, count: int = 3):
    payload = {
        "date": day,
        "title": "删除测试",
        "blocks": [{
            "title": "傍晚与夜里",
            "items": [
                {
                    "title": f"小项 {index}",
                    "instruction": "测试",
                    "schedule": {"type": "exact", "at": f"{18 + index:02d}:00"},
                    "target": "qq:dm:10001",
                }
                for index in range(count)
            ],
        }],
    }
    return await runtime.plans.apply_plan("persona-a", payload, actor="user", expected_revision=0)


@pytest.mark.asyncio
async def test_user_delete_item_is_soft_and_audited(tmp_path):
    runtime = FakeRuntime(tmp_path)
    await runtime.store.initialize()
    day = "2026-11-18"
    try:
        result = await make_plan(runtime, day, 3)
        item = result["plan"]["blocks"][0]["items"][0]
        deleted = await runtime.plans.delete_item("persona-a", item["id"], actor="user", reason="用户删除")
        assert deleted["diff"][0]["op"] == "removed"
        plan = await runtime.plans.get_plan_by_date("persona-a", day)
        assert len(plan["blocks"][0]["items"]) == 2
        history = await runtime.plans.get_plan_by_date("persona-a", day, include_deleted=True)
        assert len(history["blocks"][0]["items"]) == 3
        changes = await runtime.plans.recent_changes("persona-a", day, 1)
        assert changes[0]["reason"] == "用户删除"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_bot_delete_item_respects_minimum_and_rolls_back(tmp_path):
    runtime = FakeRuntime(tmp_path)
    await runtime.store.initialize()
    day = "2026-11-18"
    try:
        result = await make_plan(runtime, day, 3)
        items = result["plan"]["blocks"][0]["items"]
        await runtime.plans.delete_item("persona-a", items[0]["id"], actor="bot", reason="bot 删除")
        with pytest.raises(KRDError) as exc:
            await runtime.plans.delete_item("persona-a", items[1]["id"], actor="bot", reason="bot 删除")
        assert exc.value.code == "item_count"
        assert exc.value.details["actual"] == 1
        assert exc.value.details["required_min"] == 2
        plan = await runtime.plans.get_plan_by_date("persona-a", day)
        assert len(plan["blocks"][0]["items"]) == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_user_delete_block_hides_pending_but_keeps_history(tmp_path):
    runtime = FakeRuntime(tmp_path)
    await runtime.store.initialize()
    day = "2026-11-18"
    try:
        result = await make_plan(runtime, day, 3)
        block = result["plan"]["blocks"][0]
        deleted = await runtime.plans.delete_block("persona-a", block["id"], actor="user", reason="删除时段")
        assert deleted["plan"]["blocks"] == []
        active = await runtime.plans.get_plan_by_date("persona-a", day)
        assert active["blocks"] == []
        history = await runtime.plans.get_plan_by_date("persona-a", day, include_deleted=True)
        assert history["blocks"][0]["meta"]["deleted"] is True
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_user_delete_day_can_be_replanned_without_unique_conflict(tmp_path):
    runtime = FakeRuntime(tmp_path)
    await runtime.store.initialize()
    day = "2026-11-18"
    try:
        first = await make_plan(runtime, day, 2)
        deleted = await runtime.plans.delete_day("persona-a", day, reason="删除整天")
        assert deleted["deleted"] is True
        assert await runtime.plans.get_plan_by_date("persona-a", day) is None
        history = await runtime.plans.get_plan_by_date("persona-a", day, include_deleted=True)
        assert history["state"] == "deleted"
        second = await runtime.plans.apply_plan(
            "persona-a", {"date": day, "title": "重新安排", "blocks": [{"title": "新时段", "items": [
                {"title": "A", "instruction": "a", "schedule": {"type": "exact", "at": "18:00"}, "target": "qq:dm:10001"},
                {"title": "B", "instruction": "b", "schedule": {"type": "exact", "at": "20:00"}, "target": "qq:dm:10001"},
            ]}]}, actor="user", expected_revision=0)
        assert second["revision"] == first["revision"] + 2
        assert second["plan"]["title"] == "重新安排"
        assert len(second["plan"]["blocks"]) == 1
    finally:
        await runtime.close()
