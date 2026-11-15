from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Response
from fastapi.routing import APIRoute, APIWebSocketRoute


def framework_test(framework: Path, plugin_root: Path):
    os.chdir(framework)
    (framework / "data").mkdir(exist_ok=True)
    sys.path.insert(0, str(framework))
    from core.agent.func_tool_manager import FuncToolManager
    from core.config import KiraConfig
    from core.plugin import PluginManager

    try:
        tool_manager = FuncToolManager()
    except TypeError:
        tool_manager = FuncToolManager(KiraConfig({}))

    class PersonaManager:
        async def get_active_persona(self):
            return SimpleNamespace(id="default", name="Default")
        async def get_persona(self):
            return SimpleNamespace(id="default", name="Default")
        async def list_personas(self):
            return [SimpleNamespace(id="default", name="Default", is_active=True)]
        async def get_reference_image(self, persona_id):
            return None

    class SessionManager:
        async def get_sessions(self, include_content=False, kind=None):
            return [SimpleNamespace(sid="qq:dm:10001", session_title="测试会话", adapter_name="qq")]
        async def resolve_session(self, target):
            from core.chat import Session
            return Session(adapter_name="qq", session_type="dm", session_id="10001")

    class AdapterManager:
        def get_adapters(self): return {}
        def get_adapter(self, name): return None

    class EventBus:
        def __init__(self): self.events = []
        async def publish(self, event): self.events.append(event)

    async def main():
        root = Path(tempfile.mkdtemp(prefix="krd-framework-"))
        data_dir = root / "plugin_data" / "kira_rhythm_Date"
        data_dir.mkdir(parents=True)
        ctx = SimpleNamespace(
            session_mgr=SessionManager(), persona_mgr=PersonaManager(), adapter_mgr=AdapterManager(),
            event_bus=EventBus(), tool_mgr=tool_manager, plugin_mgr=None,
            get_plugin_data_dir=lambda: data_dir,
        )
        manager = PluginManager(ctx)
        ctx.plugin_mgr = manager
        app = FastAPI()
        manager.set_web_app(app)
        loaded = await manager.load_plugin_from_dir(plugin_root, auto_install=False)
        assert loaded == "kira_rhythm_Date", loaded
        instance = manager.plugin_instances[loaded]
        assert instance.runtime is not None
        assert instance.runtime.scheduler.running
        tool_names = {tool.name for tool in ctx.tool_mgr.tool_set.tools}
        assert {"rhythm_plan", "rhythm_update", "rhythm_view"} <= tool_names, tool_names
        paths = {route.path for route in app.routes}
        assert "/page/plugin/kira_rhythm_Date/dashboard" in paths
        assert "/api/plugin/kira_rhythm_Date/v1/bootstrap" in paths
        assert "/ws/plugin/kira_rhythm_Date/v1/events" in paths
        assert any(path.startswith("/static/plugin/kira_rhythm_Date/assets") for path in paths)
        bootstrap = await instance.api_bootstrap()
        assert bootstrap["ready"] and bootstrap["persona_id"] == "default"
        assert bootstrap["config"]["max_items"] == 12
        assert bootstrap["avatar"]["source"] == "builtin"
        avatar_response = Response()
        avatar = await instance.api_avatar(avatar_response, persona="default", refresh=True)
        assert avatar["source"] == "builtin"
        assert avatar_response.headers["cache-control"] == "no-store, max-age=0"
        changed = await instance.api_update_config({"patch": {"max_items": 13}, "expected_revision": 0}, persona="default")
        assert changed["config"]["max_items"] == 13 and changed["revision"] == 1
        try:
            await instance.api_update_config({"patch": {"max_items": 14}, "expected_revision": 0}, persona="default")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 409, exc
        else:
            raise AssertionError("stale config revision was not rejected")
        template = await instance.api_save_template({"name": "我的节奏", "plan": {"date": "2099-01-01", "blocks": []}}, persona="default")
        assert template["custom"] is True
        templates = await instance.api_templates(persona="default")
        assert len(templates) == 1 and templates[0]["name"] == "我的节奏"
        await instance.api_delete_template(template["id"], persona="default")
        assert await instance.api_templates(persona="default") == []
        api_routes = [route for route in app.routes if isinstance(route, APIRoute) and route.path.startswith("/api/plugin/kira_rhythm_Date")]
        assert api_routes and all(route.dependencies for route in api_routes), "An API route lacks authentication dependency"
        ws_routes = [route for route in app.routes if isinstance(route, APIWebSocketRoute) and route.path.startswith("/ws/plugin/kira_rhythm_Date")]
        assert ws_routes and all(route.dependencies for route in ws_routes), "WebSocket lacks authentication dependency"
        await manager.terminate(loaded)
        assert instance.runtime is None
        print("FRAMEWORK SMOKE OK", framework.name, "routes", len(paths), "tools", len(tool_names))

    asyncio.run(main())


if __name__ == "__main__":
    framework_test(Path(sys.argv[1]), Path(sys.argv[2]))
