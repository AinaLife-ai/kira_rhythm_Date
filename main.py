from __future__ import annotations

import sys
from pathlib import Path

from core.plugin import BasePlugin, Priority, on, register

_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

# Importing this module registers the three LLM tools against this plugin's manifest.
from krd import tools as _tools  # noqa: F401

# Canonical LLM-facing plan input: flat items with an optional block label.
# Storage remains blocks[].items[] internally for UI/API compatibility.
PLAN_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "block": {"type": "string", "description": "可选分组名；同名小项归入同一组，省略时归入“生活片段”。"},
        "title": {"type": "string", "description": "小项标题。"},
        "intent": {"type": "string", "description": "为什么安排这个小项。"},
        "instruction": {"type": "string", "description": "小项触发时具体做什么。"},
        "at": {"type": "string", "description": "精确本地时间 HH:MM 或 HH:MM:SS；与 start/end 二选一。"},
        "start": {"type": "string", "description": "时间窗开始 HH:MM 或 HH:MM:SS。"},
        "end": {"type": "string", "description": "时间窗结束 HH:MM 或 HH:MM:SS。"},
        "occurrences": {"type": "integer", "minimum": 1, "maximum": 100, "description": "时间窗展开的小项数量，默认 1。"},
        "window_mode": {"type": "string", "enum": ["single_random", "interval_random"], "description": "时间窗采样方式。"},
        "interval_seconds": {"type": "array", "items": {"type": "number", "exclusiveMinimum": 0}, "minItems": 2, "maxItems": 2, "description": "interval_random 的最小/最大间隔（秒）。"},
        "target": {"type": "string", "description": "目标会话 ID；留空使用执行池。"},
        "interaction": {"type": "string", "enum": ["auto", "must_message", "silent"], "description": "互动方式。"},
        "probability": {"type": "number", "minimum": 0, "maximum": 1, "description": "执行概率，默认 1。"},
        "category": {"type": "string", "description": "可选分类标签。"},
        "thread_id": {"type": "string", "description": "可选：本次小项推进的目标/约定 id；不关联也可以。目标层启用时有效。"}
    },
    "required": ["title"],
    "description": "时间只能二选一：at，或 start+end；不要把字段再包进 schedule。"
}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "日期，格式 YYYY-MM-DD。"},
        "title": {"type": "string"},
        "overview": {"type": "string"},
        "planned_appearance": {"type": "string"},
        "planned_mood": {"type": "string"},
        "items": {"type": "array", "minItems": 1, "maxItems": 500, "items": PLAN_ITEM_SCHEMA}
    },
    "required": ["date", "items"],
    "description": "单日计划，使用扁平 items[]；不要使用 blocks 或 schedule 包装。"
}
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
        description="创建或修订生活计划；已有 Plan 是修订。使用 plans:[{date,title,items:[...]}]；items 为扁平小项，block 可选，时间用 at 或 start/end，不要嵌套 schedule，目标层启用时可用 thread_id 关联目标/约定。用户指定日期时优先该日；规划部分的首要目标是 focus.date。at/start/end 支持 HH:MM 或 HH:MM:SS，interval_seconds 支持秒。上下文包含 threads_requiring_response 时必须先逐条回应；只有 threads_reference 时不要求回应。reject 模式下未覆盖会返回 thread_response_required，warn 模式只警告。",
        params={"type": "object", "properties": {
            "plans": {"type": "array", "items": PLAN_SCHEMA, "minItems": 1, "maxItems": 31},
            "mode": {"type": "string", "enum": ["create", "create_missing", "revise", "merge", "replace"], "default": "revise"},
            "reason": {"type": "string"}
        }, "required": ["plans"], "description": "使用 plans 数组；每个计划使用扁平 items[]，不要嵌套 blocks 或 schedule。"},
    )
    async def rhythm_plan(self, event, **kwargs):
        return await _tools.rhythm_plan(event, **kwargs)

    @register.tool(
        name="rhythm_update",
        description="主动调整后续日程、DayState，回应目标/约定，或记录确有后续价值的梦与体验。operations[].type 支持 day_state、record_experience、update_item、append_item、delete_item、delete_block、thread_add、thread_touch、thread_update、thread_close、thread_response；整天删除仅限用户，bot 不可 delete_day。删除若低于最小项数/必需时段会返回错误，需同事务替换或重新规划。上下文包含 threads_requiring_response 时，thread_response 必须逐条回应：advance/defer/waiting/no_change + 一句原因；只有 threads_reference 时不要求回应；未覆盖会返回 thread_response_missing。目标/约定启用时，thread_add 可带 dossier（档案正文）；thread_update 可改 dossier/next_step/due_at/priority/status；thread_touch 追加打卡记录（执行小项时带 item_id）；thread_close 完成或放弃。修改时间时 schedule.at/start/end 支持 HH:MM 或 HH:MM:SS。计划输入使用扁平 items[]，不要使用 blocks 包装。",
        params={"type": "object", "properties": {"operations": {"type": "array", "items": {"type": "object"}}, "reason": {"type": "string"}}, "required": ["operations"]},
    )
    async def rhythm_update(self, event, **kwargs):
        return await _tools.rhythm_update(event, **kwargs)

    @register.tool(
        name="rhythm_view",
        description="按需查看当前日型、DayState、本组、计划、历史、diff、预算、目标/约定或私有体验。",
        params={"type": "object", "properties": {"scope": {"type": "string", "enum": ["calendar", "current", "today", "block", "day", "range", "history", "diff", "quota", "experiences", "threads", "thread"], "default": "current"}, "date": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "plan_id": {"type": "string"}, "item_id": {"type": "string"}, "thread_id": {"type": "string"}, "status": {"type": "string", "enum": ["open", "paused", "done", "dropped", "deleted"]}, "kind": {"type": "string", "enum": ["goal", "promise", "project", "habit", "open_loop", "mystery"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}},
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
