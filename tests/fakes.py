from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.adapter.adapter_info import AdapterInfo
from core.chat import Session

from krd.context import ContextBuilder
from krd.plans import PlanService
from krd.policy import SessionPolicy
from krd.scheduler import Scheduler
from krd.store import Store


class FakePersonaManager:
    def __init__(self): self.active = "persona-a"
    async def get_active_persona(self): return SimpleNamespace(id=self.active, name=self.active)
    async def get_persona(self): return SimpleNamespace(id=self.active, name=self.active)
    async def list_personas(self): return [SimpleNamespace(id=self.active, name=self.active, is_active=True)]
    async def get_reference_image(self, persona_id): return None


class FakeSessionManager:
    async def get_sessions(self, include_content=False, kind=None):
        return [SimpleNamespace(sid="qq:dm:10001", session_title="测试会话", adapter_name="qq")]
    async def resolve_session(self, target): return Session(adapter_name="qq", session_type="dm", session_id="10001")


class FakeCapability:
    def is_allowed(self, *args, **kwargs): return True
    async def get_message_metadata(self): return SimpleNamespace(supported_elements=["text"])


class FakeAdapter:
    def __init__(self):
        self.info = AdapterInfo(enabled=True, adapter_id="qq", name="qq", platform="QQ")
        self.config = {"self_id": "99999"}
        self.is_running = True
        self.bot = None
    def get_capability(self, kind): return FakeCapability()


class FakeAdapterManager:
    def __init__(self): self.adapter = FakeAdapter()
    def get_adapter(self, name): return self.adapter
    def get_adapters(self): return {"qq": self.adapter}


class FakeBus:
    def __init__(self): self.events = []
    async def publish(self, event): self.events.append(event)


class FakeRuntime:
    def __init__(self, root: Path):
        self.ctx = SimpleNamespace(session_mgr=FakeSessionManager(), persona_mgr=FakePersonaManager(), adapter_mgr=FakeAdapterManager(), event_bus=FakeBus())
        self.store = Store(root / "test.db")
        self.policy = SessionPolicy(self.store, self.ctx)
        self.plans = PlanService(self.store, self.policy)
        self.context_builder = ContextBuilder(self.store, self.plans)
        self.scheduler = Scheduler(self)
        self.plans.on_change = self.scheduler.wake
        self.notices = []
    async def active_persona_id(self): return self.ctx.persona_mgr.active
    async def broadcast(self, kind, payload): self.notices.append((kind, payload))
    def log(self, *args, **kwargs): pass
    async def close(self): await self.store.close()


async def create_due_plan(runtime: FakeRuntime, *, probability=1.0, interaction="auto", count=2):
    from datetime import datetime, timedelta
    day = (datetime.now().date() + timedelta(days=1)).isoformat()
    payload = {"date": day, "title": "测试生活", "blocks": [{"title": "测试组", "items": [
        {"title": f"小项 {index}", "instruction": "自然行动", "schedule": {"type": "exact", "at": f"0{index + 7}:00"},
         "target": "qq:dm:10001", "interaction": interaction, "execution_probability": probability}
        for index in range(count)
    ]}]}
    result = await runtime.plans.apply_plan("persona-a", payload, actor="user", expected_revision=0)
    for block in result["plan"]["blocks"]:
        for item in block["items"]:
            await runtime.store.execute("UPDATE items SET scheduled_at=? WHERE id=?", (__import__('time').time() - 1, item["id"]))
    return result["plan"]
