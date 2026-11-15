from __future__ import annotations

import pytest

from core.agent.tool import ToolSet
from core.chat import KiraIMMessage, KiraMessageBatchEvent, MessageChain, Session, User
from core.chat.message_elements import Text
from core.prompt_manager import Prompt
from core.provider import LLMRequest

from krd.runtime import Runtime
from .fakes import FakeRuntime


def request_with_marker():
    return LLMRequest(
        messages=[], tool_set=ToolSet(),
        system_prompt=[Prompt("静态工具区", name="tools", source="system")],
        user_prompt=[Prompt("[生活节律｜系统触发]\n", name="message", source="system")],
    )


def planning_event(runtime, history="notice"):
    session = Session(adapter_name="qq", session_type="dm", session_id="10001")
    marker = {"run_id": "prn_test", "kind": "planning", "persona_id": "persona-a", "item_id": "", "plan_id": "", "date": "2099-01-01", "trigger_id": "test"}
    message = KiraIMMessage(message_id="krd:test", self_id="99999", chain=MessageChain([Text("[生活节律｜系统触发]\n")]),
                            timestamp=1, sender=User("system_krd", "生活节律"), is_notice=True, is_mentioned=True,
                            extra={"krd": marker})
    return KiraMessageBatchEvent(supported_elements=["text"], timestamp=1, adapter=runtime.ctx.adapter_mgr.adapter.info,
                                 session=session, messages=[message])


@pytest.mark.asyncio
async def test_dynamic_context_is_nonpersistent_and_notice_marker_is_kept(tmp_path):
    fake = FakeRuntime(tmp_path)
    runtime = Runtime(fake.ctx, tmp_path)
    await runtime.store.initialize()
    event = planning_event(fake)
    req = request_with_marker()
    await runtime.on_llm_request(event, req)
    dynamic = [prompt for prompt in req.user_prompt if prompt.name.startswith("krd_planning")]
    assert dynamic and all(not prompt.persist for prompt in dynamic)
    assert req.user_prompt[0].persist
    assert "KRD 生活节律" in req.system_prompt[0].content
    req.assemble_prompt()
    persisted = "".join(prompt.to_string() for prompt in req.user_prompt if prompt.persist)
    assert persisted.strip() == "[生活节律｜系统触发]"
    assert "previous_plans" not in persisted
    await runtime.store.close()


@pytest.mark.asyncio
async def test_none_mode_only_changes_current_marker(tmp_path):
    fake = FakeRuntime(tmp_path)
    runtime = Runtime(fake.ctx, tmp_path)
    await runtime.store.initialize()
    await runtime.store.update_config("persona-a", {"history_mode": "none"}, 0)
    req = request_with_marker()
    await runtime.on_llm_request(planning_event(fake), req)
    assert not req.user_prompt[0].persist
    dynamic = [prompt for prompt in req.user_prompt if prompt.name.startswith("krd_planning")]
    assert dynamic and all(not prompt.persist for prompt in dynamic)
    await runtime.store.close()


@pytest.mark.asyncio
async def test_normal_chat_day_state_is_nonpersistent(tmp_path):
    fake = FakeRuntime(tmp_path)
    runtime = Runtime(fake.ctx, tmp_path)
    await runtime.store.initialize()
    event = KiraMessageBatchEvent(supported_elements=["text"], timestamp=1, adapter=fake.ctx.adapter_mgr.adapter.info,
                                  session=Session(adapter_name="qq", session_type="dm", session_id="10001"), messages=[])
    req = LLMRequest(messages=[], tool_set=ToolSet(), system_prompt=[Prompt("静态工具区", name="tools")], user_prompt=[])
    await runtime.on_llm_request(event, req)
    assert len(req.user_prompt) == 1 and req.user_prompt[0].name == "krd_day_state" and not req.user_prompt[0].persist
    await runtime.store.close()
