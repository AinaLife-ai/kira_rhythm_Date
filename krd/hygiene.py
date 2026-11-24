from __future__ import annotations

import asyncio
import inspect
from typing import Any

from core.plugin import logger

from .store import Store

KRD_TRIGGER = "[生活节律｜系统触发]"
KRD_TOOL_NAMES = {"rhythm_plan", "rhythm_update", "rhythm_view"}


class MemoryHygiene:
    """Keep planning turns in chat memory as one short fact, not full plan JSON.

    KiraAI persists assistant tool calls in session.content. ``max_memory_length``
    then replays the last N planning turns with their complete ``rhythm_plan``
    arguments. KRD keeps the plan itself in SQLite and in the planning context;
    chat memory only needs the fact that a plan happened.
    """

    def __init__(self, ctx, store: Store):
        self.ctx = ctx
        self.store = store
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    @staticmethod
    def _content(message: dict[str, Any]) -> str:
        value = message.get("content")
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return " ".join(str(part.get("text", "")) for part in value if isinstance(part, dict))
        return ""

    @staticmethod
    def _tool_names(message: dict[str, Any]) -> set[str]:
        result = set()
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else call
            name = function.get("name") if isinstance(function, dict) else ""
            if name:
                result.add(str(name))
        return result

    def _is_planning_chunk(self, chunk: list[dict[str, Any]]) -> bool:
        if not isinstance(chunk, list) or not chunk or not all(isinstance(message, dict) for message in chunk):
            return False
        users = [message for message in chunk if message.get("role") == "user"]
        users = [message for message in users if self._content(message).strip()]
        has_trigger = any(self._content(message).lstrip().startswith(KRD_TRIGGER) for message in users)
        has_tool = any(self._tool_names(message) & KRD_TOOL_NAMES
                       for message in chunk if message.get("role") == "assistant")
        if not has_tool:
            return False
        if has_trigger:
            # Never drop a mixed chat turn; only the dedicated system trigger is safe.
            return all(self._content(message).lstrip().startswith(KRD_TRIGGER) for message in users)
        return not users

    async def _summary(self, persona_id: str) -> str:
        run = await self.store.one(
            "SELECT target_date FROM planning_runs WHERE persona_id=? AND kind<>'review' "
            "ORDER BY created_at DESC LIMIT 1", (persona_id,))
        if not run:
            return "[KRD] 上次规划已提交。详情见本轮 KRD 上下文。"
        day = run.get("target_date", "")
        plan = await self.store.one("SELECT id FROM plans WHERE persona_id=? AND date=?", (persona_id, day))
        if not plan:
            return f"[KRD] 上次规划 {day} 已提交。详情见本轮 KRD 上下文。"
        counts = await self.store.one(
            "SELECT COUNT(*) AS total,"
            "SUM(CASE WHEN state IN ('triggered','triggered_silent') THEN 1 ELSE 0 END) AS done,"
            "SUM(CASE WHEN state='missed' THEN 1 ELSE 0 END) AS missed "
            "FROM items WHERE plan_id=? AND state<>'deleted'", (plan["id"],))
        total = int(counts["total"] or 0) if counts else 0
        done = int(counts["done"] or 0) if counts else 0
        missed = int(counts["missed"] or 0) if counts else 0
        missed_titles = []
        if missed:
            rows = await self.store.all(
                "SELECT title FROM items WHERE plan_id=? AND state='missed' ORDER BY scheduled_at LIMIT 2",
                (plan["id"],))
            missed_titles = [str(row.get("title") or "")[:30] for row in rows if row.get("title")]
        suffix = ""
        if missed:
            suffix = f"，未完成 {missed}" + (f"（{'、'.join(missed_titles)}）" if missed_titles else "")
        return f"[KRD] 上次规划 {day}：{total} 项，完成 {done}{suffix}。详情见本轮 KRD 上下文。"

    async def prepare(self, session_id: str, persona_id: str) -> bool:
        if not session_id or not persona_id:
            return False
        try:
            config = await self.store.get_config(persona_id)
            if config.get("memory_hygiene", "summary") != "summary":
                return False
            manager = self.ctx.session_mgr
            if not hasattr(manager, "get_session") or not hasattr(manager, "update_session"):
                return False
            parameters = inspect.signature(manager.update_session).parameters
            if "content" not in parameters:
                return False
            async with self._lock(session_id):
                session = await manager.get_session(session_id, ensure_session=True)
                chunks = getattr(session, "content", None)
                if not isinstance(chunks, list) or not chunks:
                    return False
                summary = await self._summary(persona_id)
                kept: list[list[dict[str, Any]]] = []
                last_planning = -1
                for index, chunk in enumerate(chunks):
                    if self._is_planning_chunk(chunk):
                        last_planning = index
                if last_planning < 0:
                    return False
                for index, chunk in enumerate(chunks):
                    if not self._is_planning_chunk(chunk):
                        kept.append(chunk)
                    elif index == last_planning:
                        kept.append([
                            {"role": "user", "content": KRD_TRIGGER},
                            {"role": "assistant", "content": summary},
                        ])
                if kept == chunks:
                    return False
                await manager.update_session(session_id, content=kept)
                return True
        except Exception as exc:
            logger.warning("KRD memory hygiene skipped (%s: %s)", type(exc).__name__, exc)
            return False
