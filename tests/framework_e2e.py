from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI


def run(framework: Path, plugin_root: Path):
    os.chdir(framework)
    (framework / "data").mkdir(exist_ok=True)
    sys.path.insert(0, str(plugin_root))
    sys.path.insert(0, str(framework))
    from core.agent.func_tool_manager import FuncToolManager
    from core.chat import KiraIMSentResult, MessageChain
    from core.chat.message_elements import Text
    from core.chat.session import Session
    from core.chat.session_manager import SessionManager
    from core.config import KiraConfig
    from core.message_manager import MessageProcessor
    from core.plugin import PluginManager
    from core.provider import LLMResponse
    from core.workflow.src.im.workflow import DefaultIMWorkflow
    from tests import im_workflow_helpers
    make_workflow_context = im_workflow_helpers.make_workflow_context
    make_message_router = getattr(im_workflow_helpers, "make_message_router", None)
    import importlib.util
    spec = importlib.util.spec_from_file_location("krd_test_fakes", plugin_root / "tests" / "fakes.py")
    fakes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fakes)
    FakeAdapterManager, FakePersonaManager, create_due_plan = fakes.FakeAdapterManager, fakes.FakePersonaManager, fakes.create_due_plan

    async def main():
        root = Path(tempfile.mkdtemp(prefix="krd-e2e-"))
        config = SimpleNamespace(get_config=lambda key, default=None: {
            "bot_config.agent.max_tool_loop": 2,
            "bot_config.bot.min_message_delay": 0,
            "bot_config.bot.max_message_delay": 0,
        }.get(key, default))
        model = SimpleNamespace(
            model=SimpleNamespace(provider_name="test", model_id="test", model_name="test"),
            chat=AsyncMock(side_effect=lambda request: LLMResponse("<msg><text>已触发</text></msg>")),
        )
        session_manager = SimpleNamespace(
            get_session=AsyncMock(side_effect=lambda sid, *, ensure_session=False, include_content=True: Session(
                *sid.split(":", 2), session_title="Chat", internal_id="sess_test")),
            update_session=AsyncMock(), get_effective_capabilities=AsyncMock(side_effect=lambda sid, default: default),
            update_memory=AsyncMock(),
            get_sessions=AsyncMock(return_value=[SimpleNamespace(sid="qq:dm:10001", session_title="Chat", adapter_name="qq")]),
        )
        if hasattr(SessionManager, "resolve_session"):
            session_manager.resolve_session = SessionManager.resolve_session.__get__(session_manager)
        services = make_workflow_context(
            config=config, session_manager=session_manager,
            provider_mgr=SimpleNamespace(get_default_llm=lambda: model),
            prompt_manager=SimpleNamespace(get_agent_prompt=AsyncMock(return_value=[])),
            skills_manager=SimpleNamespace(skills_info=[]),
            mcp_manager=SimpleNamespace(get_tool_server_map=dict),
            db=SimpleNamespace(add_telemetry_llm_usage=AsyncMock()),
            message_history=SimpleNamespace(record_incoming_safely=AsyncMock(side_effect=lambda msg, *_: msg.message_id), link_incoming_messages=AsyncMock()),
        )
        services.message_delivery.parse_xml = AsyncMock(return_value=[MessageChain([Text("已触发")])])
        services.message_delivery.send_message_chain = AsyncMock(return_value=KiraIMSentResult("sent-id"))
        services.message_media.build_native_content = AsyncMock(return_value=[])
        workflow = DefaultIMWorkflow(services)
        if make_message_router:
            processor = MessageProcessor(workflow, message_router=make_message_router(
                adapter_mgr=services.message_delivery.adapter_mgr, message_delivery=services.message_delivery, workflow=workflow))
        else:
            processor = MessageProcessor(workflow)
        assert processor is not None
        try:
            tool_manager = FuncToolManager()
        except TypeError:
            tool_manager = FuncToolManager(KiraConfig({}))
        ctx = SimpleNamespace(
            session_mgr=session_manager, persona_mgr=FakePersonaManager(), adapter_mgr=FakeAdapterManager(),
            event_bus=services.event_bus, tool_mgr=tool_manager, plugin_mgr=None,
            get_plugin_data_dir=lambda: root / "plugin_data" / "kira_rhythm_Date",
        )
        (ctx.get_plugin_data_dir()).mkdir(parents=True)
        manager = PluginManager(ctx)
        ctx.plugin_mgr = manager
        manager.set_web_app(FastAPI())
        loaded = await manager.load_plugin_from_dir(plugin_root, auto_install=False)
        assert loaded == "kira_rhythm_Date"
        services.tool_manager = tool_manager
        runtime = manager.plugin_instances[loaded].runtime
        plan = await create_due_plan(runtime, count=1)
        item = plan["blocks"][0]["items"][0]
        run = await runtime.scheduler.claim_item(item["id"])
        event = services.event_bus.publish.await_args.args[0]
        await workflow.handle_batch_event(event)
        row = await runtime.store.one("SELECT state FROM items WHERE id=?", (item["id"],))
        assert row["state"] == "triggered", row
        receipt = await runtime.store.one("SELECT status,raw_output FROM runs WHERE id=?", (run["id"],))
        assert receipt["status"] == "finalized"
        memory = session_manager.update_memory.call_args.args[1]
        assert "生活节律｜系统触发" in memory[0].content
        assert "current_item" not in memory[0].content
        assert model.chat.await_count == 1
        services.message_delivery.send_message_chain.assert_awaited()
        planning = await runtime.scheduler.trigger_planning(
            "persona-a", "manual", plan["date"], "E2E planning revision")
        planning_event = services.event_bus.publish.await_args.args[0]
        marker = runtime.context_builder.metadata(planning_event)[0]
        assert marker["kind"] == "planning" and marker["run_id"] == planning["id"]
        await workflow.handle_batch_event(planning_event)
        planning_receipt = await runtime.store.one("SELECT status FROM planning_runs WHERE id=?", (planning["id"],))
        assert planning_receipt["status"] == "no_change"
        assert model.chat.await_count == 2
        await manager.terminate(loaded)
        print("FRAMEWORK E2E OK", framework.name, "item + planning", "memory_messages", len(memory))

    asyncio.run(main())


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
