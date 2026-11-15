from __future__ import annotations

import sys
from pathlib import Path

from core.plugin import BasePlugin, Priority, on, register

_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

# Importing this module registers the three LLM tools against this plugin's manifest.
from krd import tools as _tools  # noqa: F401
from krd.runtime import Runtime
from krd.api_methods import ApiMixin


class KRDPlugin(ApiMixin, BasePlugin):
    def __init__(self, ctx, cfg: dict):
        super().__init__(ctx, cfg)
        self.runtime: Runtime | None = None

    async def initialize(self):
        data_dir = self.ctx.get_plugin_data_dir()
        self.runtime = Runtime(
            self.ctx, data_dir, debug=bool(self.plugin_cfg.get("debug_log", False)),
            plugin_cfg=self.plugin_cfg,
        )
        await self.runtime.initialize()

    async def terminate(self):
        if self.runtime is not None:
            await self.runtime.close()
            self.runtime = None

    @register.tool(
        name="rhythm_plan",
        description="创建或修订自己接下来的完整生活计划；已有 Plan 是修订。plan 必须是 {date, blocks:[{title, items:[...]}]}，小项放在 blocks[].items[]，不要放 plan 顶层 items。支持 plans[] 多日原子提交。用户指定某日时优先处理该日。精确时间 at 与时间窗 start/end 均支持 HH:MM 或 HH:MM:SS；随机间隔可用 interval_seconds 精确到秒。",
        params={"type": "object", "properties": {"plan": {"type": "object", "description": "Must use date + blocks[].items[]; items cannot be at plan root."}, "plans": {"type": "array", "items": {"type": "object"}}, "mode": {"type": "string", "enum": ["create", "create_missing", "revise", "merge", "replace"], "default": "revise"}, "reason": {"type": "string"}}},
    )
    async def rhythm_plan(self, event, **kwargs):
        return await _tools.rhythm_plan(event, **kwargs)

    @register.tool(
        name="rhythm_update",
        description="主动调整后续日程、DayState，或记录确有后续价值的梦与体验。修改时间时 schedule.at/start/end 支持 HH:MM 或 HH:MM:SS。新建/修订计划同样使用 blocks[].items[] 结构。",
        params={"type": "object", "properties": {"operations": {"type": "array", "items": {"type": "object"}}, "reason": {"type": "string"}}, "required": ["operations"]},
    )
    async def rhythm_update(self, event, **kwargs):
        return await _tools.rhythm_update(event, **kwargs)

    @register.tool(
        name="rhythm_view",
        description="按需查看当前日型、DayState、本组、计划、历史、diff、预算或私有体验。",
        params={"type": "object", "properties": {"scope": {"type": "string", "enum": ["calendar", "current", "today", "block", "day", "range", "history", "diff", "quota", "experiences"], "default": "current"}, "date": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "plan_id": {"type": "string"}, "item_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}},
    )
    async def rhythm_view(self, event, **kwargs):
        return await _tools.rhythm_view(event, **kwargs)

    @on.llm_request(priority=-70)
    async def inject_rhythm_context(self, event, req, *_):
        if self.runtime is not None:
            await self.runtime.on_llm_request(event, req)

    @on.llm_response(priority=Priority.MEDIUM)
    async def record_rhythm_response(self, event, response, *_):
        if self.runtime is not None:
            await self.runtime.on_llm_response(event, response)

    @on.final_result(priority=Priority.LOW)
    async def finalize_rhythm_run(self, event, *_):
        if self.runtime is not None:
            await self.runtime.on_final_result(event)
