from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio

from core.chat import KiraIMMessage, MessageChain, User
from core.chat.message_elements import Text
from krd.runtime import Runtime
from .fakes import FakeRuntime, create_due_plan


@pytest_asyncio.fixture
async def runtime(tmp_path):
    fake = FakeRuntime(tmp_path)
    value = Runtime(fake.ctx, tmp_path)
    await value.store.initialize()
    yield value
    await value.store.close()


@pytest.mark.asyncio
async def test_silent_pure_run_is_enforced(runtime):
    plan = await create_due_plan(runtime, interaction="silent", count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    response = SimpleNamespace(text_response="<msg><text>不应可见</text></msg>")
    await runtime.before_llm_response(event, response)
    assert response.text_response == "<msg/>"


@pytest.mark.asyncio
async def test_silent_item_never_erases_mixed_user_response(runtime):
    plan = await create_due_plan(runtime, interaction="silent", count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    event.messages.append(KiraIMMessage(
        message_id="real-user", self_id="99999", chain=MessageChain([Text("用户问题")]), timestamp=1,
        sender=User("user", "用户"), is_notice=False, is_mentioned=True))
    response = SimpleNamespace(text_response="<msg><text>给用户和我的回复</text></msg>")
    await runtime.before_llm_response(event, response)
    assert "给用户和我的回复" in response.text_response


@pytest.mark.asyncio
async def test_auto_item_is_quiet_when_delivery_window_is_active(runtime):
    await runtime.store.update_config("persona-a", {
        "quiet_delivery_windows": [{"start": "00:00", "end": "23:59"}]}, 0)
    plan = await create_due_plan(runtime, interaction="auto", count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    response = SimpleNamespace(text_response="<msg><text>白天也不可见</text></msg>", tool_calls=[], status="success")
    await runtime.before_llm_response(event, response)
    assert response.text_response == "<msg/>"
    await runtime.on_llm_response(event, response)
    run = await runtime.store.one("SELECT * FROM runs WHERE item_id=?", (item["id"],))
    assert run["status"] == "responded"
