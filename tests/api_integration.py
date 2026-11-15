from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI


def run(framework: Path, plugin_root: Path):
    os.chdir(framework)
    (framework / "data").mkdir(exist_ok=True)
    sys.path.insert(0, str(framework))
    from core.agent.func_tool_manager import FuncToolManager
    from core.config import KiraConfig
    from core.plugin import PluginManager

    class PersonaManager:
        async def get_active_persona(self): return SimpleNamespace(id="default", name="Default")
        async def get_persona(self): return SimpleNamespace(id="default", name="Default")
        async def list_personas(self): return [SimpleNamespace(id="default", name="Default")]
        async def get_reference_image(self, persona_id): return None

    class SessionManager:
        async def get_sessions(self, include_content=False, kind=None):
            return [SimpleNamespace(sid="qq:dm:10001", session_title="Chat", adapter_name="qq")]
        async def resolve_session(self, target):
            from core.chat import Session
            return Session(adapter_name="qq", session_type="dm", session_id="10001")

    class AdapterManager:
        def get_adapters(self): return {}
        def get_adapter(self, name): return None

    async def main():
        root = Path(tempfile.mkdtemp(prefix="krd-api-"))
        data_dir = root / "plugin_data" / "kira_rhythm_Date"
        data_dir.mkdir(parents=True)
        try:
            tool_manager = FuncToolManager()
        except TypeError:
            tool_manager = FuncToolManager(KiraConfig({}))
        ctx = SimpleNamespace(session_mgr=SessionManager(), persona_mgr=PersonaManager(), adapter_mgr=AdapterManager(),
                              event_bus=SimpleNamespace(publish=lambda event: asyncio.sleep(0)), tool_mgr=tool_manager,
                              plugin_mgr=None, get_plugin_data_dir=lambda: data_dir)
        manager = PluginManager(ctx)
        ctx.plugin_mgr = manager
        app = FastAPI()
        manager.set_web_app(app)
        loaded = await manager.load_plugin_from_dir(plugin_root, auto_install=False)
        for route in app.routes:
            for dependency in getattr(route, "dependencies", []):
                app.dependency_overrides[dependency.dependency] = lambda: None
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        base = "/api/plugin/kira_rhythm_Date/v1"
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"{base}/bootstrap")
            assert response.status_code == 200, response.text
            avatar = await client.get(f"{base}/avatar?refresh=1")
            assert avatar.status_code == 200 and avatar.headers["cache-control"] == "no-store, max-age=0"
            invalid = await client.put(f"{base}/config", json={"patch": {"weather": None}, "expected_revision": 0})
            assert invalid.status_code == 400 and invalid.json()["detail"]["code"] == "invalid_config"
            today = datetime.now().date().isoformat()
            day_state = await client.post(f"{base}/day-state/{today}", json={"current_mood": "平静"})
            assert day_state.status_code == 200 and day_state.json()["current_mood"] == "平静"
            readonly = await client.post(f"{base}/day-state/{today}", json={"current_mood": "x", "revision": 9})
            assert readonly.status_code == 400
            tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
            payload = {"date": tomorrow, "expected_revision": 0, "blocks": [{"title": "组", "items": [{
                "title": "API 小项", "schedule": {"type": "exact", "at": "09:00"}, "target": "qq:dm:10001",
            }]}]}
            saved = await client.post(f"{base}/plans", json=payload)
            assert saved.status_code == 200, saved.text
            result = saved.json()
            item_id = result["plan"]["blocks"][0]["items"][0]["id"]
            plans = await client.get(f"{base}/plans?start={tomorrow}&end={tomorrow}")
            assert plans.status_code == 200 and len(plans.json()) == 1
            diff = await client.get(f"{base}/plans/{result['plan']['id']}/diff?persona=other")
            assert diff.status_code == 200 and diff.json() == []
            run = await client.post(f"{base}/items/{item_id}/run")
            assert run.status_code == 400 and run.json()["detail"]["code"] == "dispatch_failed"
        await manager.terminate(loaded)
        print("API INTEGRATION OK", framework.name, "bootstrap/config/day-state/plans/diff/dispatch")

    asyncio.run(main())


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
