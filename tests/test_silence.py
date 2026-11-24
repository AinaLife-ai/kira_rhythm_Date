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
async def test_silent_output_is_prompt_only_and_visible_text_is_diagnosed(runtime):
    plan = await create_due_plan(runtime, interaction="silent", count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    prompt = await runtime.context_builder.item_prompt(runtime.context_builder.metadata(event)[0])
    assert '"effective_interaction":"silent"' in prompt
    assert '"enforcement":"prompt_only"' in prompt
    assert "不得为了本日程删除或改写给用户的回答" not in prompt
    response = SimpleNamespace(text_response="<msg><text>模型自己泄漏的文字</text></msg>", tool_calls=[], status="success")
    await runtime.on_llm_response(event, response)
    assert "模型自己泄漏的文字" in response.text_response
    receipt = await runtime.store.one("SELECT error FROM runs WHERE id=?", (run["id"],))
    stored = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert receipt["error"] == "silence_unmet" and stored["state"] == "triggered"


@pytest.mark.asyncio
async def test_mixed_user_response_is_never_rewritten(runtime):
    plan = await create_due_plan(runtime, interaction="silent", count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    event.messages.append(KiraIMMessage(
        message_id="real-user", self_id="99999", chain=MessageChain([Text("用户问题")]), timestamp=1,
        sender=User("user", "用户"), is_notice=False, is_mentioned=True))
    response = SimpleNamespace(text_response="<msg><text>给用户和我的回复</text></msg>", tool_calls=[], status="success")
    original = response.text_response
    await runtime.on_llm_response(event, response)
    assert response.text_response == original


@pytest.mark.asyncio
async def test_auto_quiet_guidance_and_actual_silent_result(runtime):
    await runtime.store.update_config("persona-a", {
        "quiet_delivery_windows": [{"start": "00:00", "end": "23:59"}]}, 0)
    plan = await create_due_plan(runtime, interaction="auto", count=1)
    item = plan["blocks"][0]["items"][0]
    run = await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    prompt = await runtime.context_builder.item_prompt(runtime.context_builder.metadata(event)[0])
    assert '"quiet_now":true' in prompt and '"effective_interaction":"silent"' in prompt
    response = SimpleNamespace(text_response="<msg/>", tool_calls=[], status="success")
    await runtime.on_llm_response(event, response)
    assert response.text_response == "<msg/>"
    receipt = await runtime.store.one("SELECT error FROM runs WHERE id=?", (run["id"],))
    stored = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert receipt["error"] == "" and stored["state"] == "triggered_silent"

@pytest.mark.asyncio
async def test_quiet_window_lets_existing_must_message_stay_silent(runtime):
    plan = await create_due_plan(runtime, interaction="must_message", count=1)
    item = plan["blocks"][0]["items"][0]
    await runtime.store.update_config(
        "persona-a", {"quiet_delivery_windows": [{"start": "00:00", "end": "23:59"}]}, 0)
    run = await runtime.scheduler.claim_item(item["id"])
    event = runtime.ctx.event_bus.events[-1]
    prompt = await runtime.context_builder.item_prompt(runtime.context_builder.metadata(event)[0])
    assert '"scheduled_interaction":"must_message"' in prompt
    assert '"effective_interaction":"silent"' in prompt
    response = SimpleNamespace(text_response="<msg/>", tool_calls=[], status="success")
    await runtime.on_llm_response(event, response)
    receipt = await runtime.store.one("SELECT error FROM runs WHERE id=?", (run["id"],))
    stored = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
    assert receipt["error"] == ""
    assert stored["state"] == "triggered_silent"
