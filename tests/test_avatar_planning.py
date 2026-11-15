from __future__ import annotations

import io

import pytest
import pytest_asyncio
from PIL import Image

from krd.avatars import AvatarService
from .fakes import FakeRuntime, create_due_plan


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    yield value
    await value.close()


@pytest.mark.asyncio
async def test_existing_next_day_plan_still_gets_daily_opportunity(runtime):
    plan = await create_due_plan(runtime, count=1)
    day = plan["date"]
    first = await runtime.scheduler.trigger_planning("persona-a", "daily", day, "每日定时", "daily:test")
    second = await runtime.scheduler.trigger_planning("persona-a", "daily", day, "每日定时", "daily:test")
    assert first["id"] == second["id"]
    followup = await runtime.scheduler.trigger_planning("persona-a", "all_triggered", day, "全部触发", "all:test")
    assert followup["id"] != first["id"]
    events = runtime.ctx.event_bus.events
    assert len(events) == 2
    assert all(ContextBuilder.metadata(event)[0]["date"] == day for event in events)


@pytest.mark.asyncio
async def test_avatar_normal_reads_use_cache_but_entry_refresh_bypasses_it(runtime, monkeypatch):
    image = Image.new("RGB", (12, 12), (140, 120, 240))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    calls = []

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url):
            calls.append(url)
            return type("Response", (), {"content": buffer.getvalue(), "raise_for_status": lambda self: None})()

    monkeypatch.setattr("krd.avatars.httpx.AsyncClient", lambda *args, **kwargs: Client())
    service = AvatarService(runtime.store, runtime.ctx, runtime.store.path.parent)
    first = await service.current("persona-a")
    second = await service.current("persona-a")
    refreshed = await service.current("persona-a", force_refresh=True)
    assert first["source"] == "adapter:qq" and second["id"] == first["id"]
    assert refreshed["id"] == first["id"]
    assert len(calls) == 2


from krd.context import ContextBuilder
