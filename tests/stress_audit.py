from __future__ import annotations

import asyncio
import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from krd.context import ContextBuilder
from .fakes import FakeRuntime


async def run():
    root = Path(tempfile.mkdtemp(prefix="krd-stress-"))
    runtime = FakeRuntime(root)
    await runtime.store.initialize()
    await runtime.store.update_config("persona-a", {"auto_plan": False}, 0)
    day = (datetime.now().date() + timedelta(days=1)).isoformat()
    blocks = []
    for block_index in range(10):
        blocks.append({"title": f"组 {block_index}", "items": [{
            "title": f"压力小项 {block_index}-{index}", "schedule": {"type": "exact", "at": "09:00"},
            "target": "qq:dm:10001", "interaction": "auto",
        } for index in range(10)]})
    started = time.perf_counter()
    result = await runtime.plans.apply_plan("persona-a", {"date": day, "blocks": blocks}, actor="user", expected_revision=0)
    save_ms = (time.perf_counter() - started) * 1000
    plan = result["plan"]
    assert sum(len(block["items"]) for block in plan["blocks"]) == 100
    started = time.perf_counter()
    for _ in range(100):
        loaded = await runtime.plans.get_plan(plan["id"], "persona-a")
        assert len(loaded["blocks"]) == 10
    read_ms = (time.perf_counter() - started) * 10
    await runtime.store.execute("UPDATE items SET scheduled_at=? WHERE plan_id=?", (time.time() - 1, plan["id"]))
    started = time.perf_counter()
    await runtime.scheduler.dispatch_due()
    dispatch_ms = (time.perf_counter() - started) * 1000
    events = [event for event in runtime.ctx.event_bus.events
              if any(item["kind"] == "item" for item in ContextBuilder.metadata(event))]
    assert len(events) == 100
    queued = await runtime.store.one("SELECT COUNT(*) AS count FROM items WHERE plan_id=? AND state='queued'", (plan["id"],))
    assert queued["count"] == 100
    await runtime.scheduler.stop()
    await runtime.close()
    print(json.dumps({"items": 100, "save_ms": round(save_ms, 2), "average_tree_read_ms": round(read_ms, 3),
                      "dispatch_100_ms": round(dispatch_ms, 2), "db_bytes": (root / "test.db").stat().st_size,
                      "events": len(events)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run())
