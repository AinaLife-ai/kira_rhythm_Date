from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from .fakes import FakeRuntime


async def run():
    runtime = FakeRuntime(Path(tempfile.mkdtemp(prefix="krd-soak-")))
    await runtime.store.initialize()
    await runtime.store.update_config("persona-a", {"auto_plan": False}, 0)
    await runtime.scheduler.start()
    await asyncio.sleep(0.15)
    before = await runtime.store.one("PRAGMA data_version")
    events_before = len(runtime.ctx.event_bus.events)
    await asyncio.sleep(31)
    after = await runtime.store.one("PRAGMA data_version")
    assert before["data_version"] == after["data_version"], (before, after)
    assert len(runtime.ctx.event_bus.events) == events_before
    assert runtime.scheduler.running and runtime.scheduler.task and not runtime.scheduler.task.done()
    await runtime.scheduler.stop()
    await runtime.close()
    print(json.dumps({"idle_seconds": 31, "data_version_before": before["data_version"],
                      "data_version_after": after["data_version"], "new_events": 0, "scheduler_alive": True}))


if __name__ == "__main__":
    asyncio.run(run())
