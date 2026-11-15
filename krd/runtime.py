from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from core.plugin import logger
from core.prompt_manager import Prompt
from core.provider import LLMRequest

from .context import ContextBuilder
from .plans import PlanService
from .policy import SessionPolicy
from .scheduler import Scheduler
from .store import Store

STATIC_TOOL_GUIDE = """
[KRD 生活节律]
你可以用 rhythm_plan 创建/修订完整生活计划，用 rhythm_update 调整后续小项、DayState 或记录梦与体验，用 rhythm_view 按需查看日程或万年历（农历、节气、法定假期）。普通模型响应即已触发，不需要完成工具；<msg/> 合法。所有修改遵守用户权限、数量、概率、日型、禁止执行/安静投递/必需覆盖规则。已有 Plan 是修订，不重复新建。上下文和工具返回的时间字段已转换为当地可读时间；修改时间请使用 schedule，不要回传时间显示字符串。
""".strip()


class Runtime:
    def __init__(self, ctx, data_dir: Path, debug: bool = False, plugin_cfg: dict | None = None):
        self.ctx = ctx
        self.data_dir = Path(data_dir)
        self.debug = debug
        self.plugin_cfg = plugin_cfg or {}
        self.store = Store(self.data_dir / "rhythm.db")
        self.policy = SessionPolicy(self.store, ctx)
        self.plans = PlanService(self.store, self.policy)
        self.weather = None
        self.avatars = None
        self.calendar = None
        self.context_builder = ContextBuilder(self.store, self.plans, None)
        self.scheduler = Scheduler(self)
        self.plans.on_change = self.scheduler.wake
        self.ws_clients: set[Any] = set()
        self._persona_cache: tuple[float, str] = (0, "")

    async def initialize(self) -> None:
        await self.store.initialize()
        from .weather import WeatherService
        from .avatars import AvatarService
        from .calendar import CalendarService
        self.weather = WeatherService(self.store, self.ctx, self.plugin_cfg)
        self.avatars = AvatarService(self.store, self.ctx, self.data_dir)
        self.calendar = CalendarService(self.store)
        self.plans.calendar = self.calendar
        self.context_builder.weather = self.weather
        self.context_builder.calendar = self.calendar
        await self.scheduler.start()
        active = await self.active_persona_id()
        if active:
            today = await self.plans.current_date(active)
            self.calendar.refresh_soon(int(today[:4]))

    async def close(self) -> None:
        await self.scheduler.stop()
        clients = list(self.ws_clients)
        self.ws_clients.clear()
        for client in clients:
            try:
                await client.close()
            except Exception:
                pass
        if self.weather is not None:
            await self.weather.close()
        if self.calendar is not None:
            await self.calendar.close()
        await self.store.close()

    def log(self, level: str, event: str, **fields: Any) -> None:
        if level == "error" or self.debug or level == "warning":
            line = f"[KRD] {event} " + " ".join(f"{key}={value}" for key, value in fields.items())
            getattr(logger, level if level in {"debug", "info", "warning", "error"} else "info")(line)

    async def active_persona_id(self) -> str:
        now = asyncio.get_running_loop().time()
        if now - self._persona_cache[0] < 1 and self._persona_cache[1]:
            return self._persona_cache[1]
        manager = self.ctx.persona_mgr
        persona = await manager.get_active_persona() if hasattr(manager, "get_active_persona") else await manager.get_persona()
        identifier = str(getattr(persona, "id", "") or "")
        self._persona_cache = (now, identifier)
        if identifier:
            await self.store.ensure_persona(identifier)
        return identifier

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.ws_clients:
            return
        dead = []
        for client in list(self.ws_clients):
            try:
                await client.send_json({"type": event_type, "payload": payload})
            except Exception:
                dead.append(client)
        for client in dead:
            self.ws_clients.discard(client)

    async def on_llm_request(self, event, req: LLMRequest) -> None:
        event._krd_runtime = self
        metadata = self.context_builder.metadata(event)
        active = await self.active_persona_id()
        base_config = await self.store.get_config(active) if active else None
        valid = [item for item in metadata if item["persona_id"] == active]
        if metadata and not valid and all((getattr(message, "extra", None) or {}).get("krd") for message in event.messages):
            event.stop()
            return
        if len(valid) != len(metadata) and req.tool_set:
            req.tool_set.remove("rhythm_plan", "rhythm_update", "rhythm_view")
        allowed_valid = []
        for item in valid:
            allowed = await self.policy.is_allowed(
                active, event.sid, "planning" if item["kind"] == "planning" else "execution", config=base_config)
            if not allowed:
                if req.tool_set:
                    req.tool_set.remove("rhythm_plan", "rhythm_update", "rhythm_view")
                continue
            allowed_valid.append(item)
            if item["kind"] == "planning":
                content = await self.context_builder.planning_prompt(item)
            elif item["kind"] == "review":
                content = await self.context_builder.review_prompt(item)
            else:
                content = await self.context_builder.item_prompt(item)
            req.user_prompt.append(Prompt(
                content, name=f"krd_{item['kind']}_{item['run_id']}", source="kira_rhythm_Date",
                persist=False, render_template=False,
            ))
            if base_config["history_mode"] == "full":
                template = (base_config["planning_review"]["prompt"] if item["kind"] == "review" else
                            base_config["planning_prompt"] if item["kind"] == "planning" else base_config["execution_prompt"])
                req.user_prompt.append(Prompt(
                    template, name="krd_full_template", source="kira_rhythm_Date", persist=True, render_template=False,
                ))
            elif base_config["history_mode"] == "none":
                message_prompts = [p for p in req.user_prompt if isinstance(p, Prompt) and p.name == "message"]
                index = item.get("message_index", 0)
                if index < len(message_prompts):
                    message_prompts[index].persist = False
        event._krd_allowed_run_ids = {item["run_id"] for item in allowed_valid}
        await self.scheduler.on_request(event)
        normal_allowed = False
        if not metadata and active:
            normal_allowed = await self.policy.is_allowed(active, event.sid, "execution", config=base_config)
            if normal_allowed:
                if base_config.get("inject_day_state", True):
                    req.user_prompt.append(Prompt(
                        await self.context_builder.compact_state(active, config=base_config), name="krd_day_state",
                        source="kira_rhythm_Date", persist=False, render_template=False,
                    ))
            elif req.tool_set:
                req.tool_set.remove("rhythm_plan", "rhythm_update", "rhythm_view")
        if allowed_valid or normal_allowed:
            for prompt in req.system_prompt:
                if prompt.name == "tools" and "KRD 生活节律" not in prompt.content:
                    prompt.content += "\n" + STATIC_TOOL_GUIDE
        elif req.tool_set:
            req.tool_set.remove("rhythm_plan", "rhythm_update", "rhythm_view")

    async def on_llm_response(self, event, response) -> None:
        active = await self.active_persona_id()
        filtered = [item for item in self.context_builder.metadata(event) if item["persona_id"] == active]
        if not filtered:
            return
        # Scheduler reads the same message metadata; inactive personas are never
        # allowed to close a different persona's run.
        await self.scheduler.on_response(event, response)

    async def on_final_result(self, event) -> None:
        await self.scheduler.on_final(event)
