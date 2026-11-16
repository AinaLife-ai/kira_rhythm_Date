from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from .plans import PlanService
from .store import Store, dumps
from .timeutils import in_active_windows, timezone
from .llm_format import prepare_llm_payload


class ContextBuilder:
    def __init__(self, store: Store, plans: PlanService, weather=None, host_timezone=None):
        self.store = store
        self.plans = plans
        self.weather = weather
        self.calendar = None
        self.host_timezone = host_timezone

    def host_timezone_name(self):
        if callable(self.host_timezone):
            try:
                return self.host_timezone()
            except Exception:
                return None
        return self.host_timezone

    @staticmethod
    def metadata(event) -> list[dict[str, Any]]:
        result = []
        for index, message in enumerate(getattr(event, "messages", []) or []):
            extra = getattr(message, "extra", None) or {}
            marker = extra.get("krd") if isinstance(extra, dict) else None
            if isinstance(marker, dict) and marker.get("run_id"):
                result.append({**marker, "message_index": index})
        return result

    @staticmethod
    def _bounded(value: Any, limit: int) -> str:
        text = value if isinstance(value, str) else dumps(value)
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 80)] + f"\n…[KRD truncated {len(text) - limit + 80} chars; use rhythm_view]"

    async def _weather(self, persona_id: str) -> Any:
        if self.weather is None:
            return None
        try:
            result = await self.weather.summary(persona_id, allow_network=False)
            if result.get("mode") == "off":
                return None
            status = (result.get("real") or {}).get("status")
            if status in {"pending", "stale"}:
                self.weather.refresh_soon(persona_id)
            return result
        except Exception:
            return {"warning": "天气暂时不可用"}

    async def _calendar_day(self, day: str) -> dict[str, Any]:
        if self.calendar is None:
            return {"date": day, "status": "disabled"}
        try:
            return await self.calendar.day(day, allow_network=False)
        except Exception as exc:
            return {"date": day, "status": "unavailable", "reason": type(exc).__name__}

    @staticmethod
    def _calendar_context(full: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        flags = config.get("calendar_context", {})
        result: dict[str, Any] = {}
        holiday = full.get("holiday") or {}
        if holiday:
            if holiday.get("is_off_day") and flags.get("holiday", True):
                result["holiday"] = {"name": holiday.get("name", ""), "is_off_day": True}
            elif not holiday.get("is_off_day") and flags.get("adjusted_workday", True):
                result["adjusted_workday"] = {"name": holiday.get("name", "")}
        if flags.get("festivals", True):
            festivals = [*full.get("solar_festivals", []), *full.get("lunar_festivals", [])]
            if festivals:
                result["festivals"] = list(dict.fromkeys(festivals))
        if flags.get("solar_terms", True) and full.get("solar_term"):
            result["solar_terms"] = [full["solar_term"]]
        if full.get("data_status") in {"stale", "unavailable"}:
            result["warning"] = "法定假期数据可能不是最新"
        return result

    async def _active_day_types(self, persona_id: str, day: str) -> list[dict[str, Any]]:
        return await self.plans.resolve_day_types(persona_id, day)

    async def _day_type_prompt(self, persona_id: str, matches: list[dict[str, Any]], mode: str) -> str:
        lines = []
        key = "planning_prompt" if mode == "planning" else "execution_prompt"
        for match in matches:
            entry = match.get("entry") or {}
            overrides = (entry.get("config") or {}).get("overrides") or {}
            prompt = str(overrides.get(key, "") or "").strip()
            if prompt:
                lines.append(f"[{match.get('name', '日型')}]\n{prompt}")
        return "\n\n".join(lines)

    @staticmethod
    def _plan_items(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
        return [item for block in (plan or {}).get("blocks", []) for item in block.get("items", [])]

    def _limits(self, config: dict[str, Any], plan: dict[str, Any] | None) -> dict[str, int]:
        return {
            "min_items": int(config["min_items"]),
            "max_items": int(config["max_items"]),
            "planned_items": len(self._plan_items(plan)),
        }

    @staticmethod
    def _clock_fields(timestamp: Any, day: str, tz_name: str) -> dict[str, str]:
        if not timestamp:
            return {}
        value = datetime.fromtimestamp(float(timestamp), timezone(tz_name))
        result = {"at": value.strftime("%H:%M:%S" if value.second else "%H:%M")}
        if value.date().isoformat() != day:
            result["on"] = value.date().isoformat()
        return result

    @staticmethod
    def _day_types_text(matches: list[dict[str, Any]]) -> str:
        return "、".join(str(item.get("name", "")).strip() for item in matches if item.get("name"))

    @staticmethod
    def _short_item_id(identifier: str) -> str:
        value = str(identifier)
        return value.split("_", 1)[-1][:12] if value.startswith("itm_") else value[:12]

    @staticmethod
    def _trigger(metadata: dict[str, Any]) -> dict[str, Any]:
        return {"reason": metadata["reason"]} if metadata.get("reason") else {}

    async def _day_type(self, persona_id: str, identifier: str) -> dict[str, Any]:
        entries = await self.store.list_day_types(persona_id)
        entry = next((item for item in entries if item["id"] == identifier), None)
        return {"id": identifier, "name": entry["name"] if entry else identifier}

    async def compact_state(self, persona_id: str, config: dict[str, Any] | None = None) -> str:
        if config is None:
            day = await self.plans.current_date(persona_id)
        else:
            from .timeutils import timezone
            day = datetime.now(timezone(self.plans.policy.timezone_name(config))).date().isoformat()
        state = await self.plans.day_state(persona_id, day)
        plan = await self.plans.get_plan_by_date(persona_id, day)
        base_config = await self.store.get_config(persona_id)
        matches = await self._active_day_types(persona_id, day)
        effective = await self.plans.effective_config(persona_id, matches[0]["id"] if matches else "")
        next_item = await self.store.one(
            "SELECT title,scheduled_at FROM items WHERE plan_id=? AND state='scheduled' ORDER BY scheduled_at LIMIT 1",
            (plan["id"],)) if plan else None
        calendar = self._calendar_context(await self._calendar_day(day), base_config)
        payload = {
            "date": day,
            "day_types": self._day_types_text(matches),
            "calendar": calendar,
            "daily_limits": self._limits(effective, plan),
            "appearance": state.get("current_appearance"), "mood": state.get("current_mood"),
            "activity": state.get("current_activity"), "note": state.get("current_note"),
            "next": ({"title": next_item["title"], **self._clock_fields(next_item["scheduled_at"], day, self.plans.policy.timezone_name(effective))} if next_item else None),
        }
        tz_name = self.plans.policy.timezone_name(effective)
        host_tz = self.host_timezone_name()
        if host_tz is None or host_tz != tz_name:
            payload["timezone"] = tz_name
        payload = prepare_llm_payload(payload, tz_name, host_tz, drop=("source",))
        return "[KRD DayState · request only]\n" + self._bounded(payload, 1400)

    async def planning_prompt(self, metadata: dict[str, Any]) -> str:
        persona_id = metadata["persona_id"]
        base_config = await self.store.get_config(persona_id)
        target_date = metadata.get("date") or await self.plans.current_date(persona_id)
        current = await self.plans.get_plan_by_date(persona_id, target_date)
        tz_name = self.plans.policy.timezone_name(base_config)
        history = []
        start = (datetime.fromisoformat(target_date) - timedelta(days=base_config["history_days"])).date().isoformat()
        end = (datetime.fromisoformat(target_date) - timedelta(days=1)).date().isoformat()
        for plan in await self.plans.list_plans(persona_id, start, end):
            history.append(self._plan_data(plan, include_instruction=False, tz_name=tz_name))
        matches = await self._active_day_types(persona_id, target_date)
        effective = await self.plans.effective_config(persona_id, matches[0]["id"] if matches else "")
        calendar = self._calendar_context(await self._calendar_day(target_date), base_config)
        payload = {
            "instruction": base_config["planning_prompt"],
            "focus": {"date": target_date,
                      "instruction": f"这次规划的首要目标是 {target_date}。先为这一天创建或修订；仍可在配置允许的范围内处理其他日期，但不要无理由跳过这一天。",
                      **({"reason": metadata["reason"]} if metadata.get("reason") else {})},
            "day_types": self._day_types_text(matches),
            "day_type_prompt": await self._day_type_prompt(persona_id, matches, "planning"),
            "calendar": calendar,
            "daily_limits": self._limits(effective, current),
            "constraints": {key: effective[key] for key in (
                "allow_exact", "allow_window", "allow_probability", "min_probability",
                "blocked_execution_windows", "quiet_delivery_windows", "required_coverage_windows")},
            "current_plan": self._plan_data(current, tz_name=tz_name) if current else None,
            "previous_plans": history,
            "weather": await self._weather(persona_id)
        }
        host_tz = self.host_timezone_name()
        if host_tz is None or host_tz != tz_name:
            payload["timezone"] = tz_name
        payload = prepare_llm_payload(payload, tz_name, host_tz, drop=("source",))
        return "[KRD planning context · request only]\n" + self._bounded(payload, base_config["history_char_budget"])

    async def review_prompt(self, metadata: dict[str, Any]) -> str:
        persona_id = metadata["persona_id"]
        target_date = metadata.get("date") or await self.plans.current_date(persona_id)
        plan = await self.plans.get_plan_by_date(persona_id, target_date)
        if not plan:
            return "[KRD review context · request only]\n{\"status\":\"plan_missing\",\"instruction\":\"仅在确有必要时创建计划；不要因为一次检查而无条件新建。\"}"
        base_config = await self.store.get_config(persona_id)
        matches = await self._active_day_types(persona_id, target_date)
        effective = await self.plans.effective_config(persona_id, matches[0]["id"] if matches else "")
        tz_name = self.plans.policy.timezone_name(effective)
        next_item = await self.store.one(
            "SELECT * FROM items WHERE plan_id=? AND state='scheduled' ORDER BY scheduled_at LIMIT 1", (plan["id"],))
        if next_item:
            from .plans import item_json
            next_item = item_json(next_item)
            next_item = {"title": next_item.get("title", ""), **self._clock_fields(next_item.get("scheduled_at"), plan["date"], tz_name)}
        quiet_now = in_active_windows(
            effective["quiet_delivery_windows"], time.time(), self.plans.policy.timezone_name(effective))
        payload = {
            "instruction": effective["planning_review"]["prompt"],
            "day_types": self._day_types_text(matches),
            "day_type_prompt": await self._day_type_prompt(persona_id, matches, "planning"),
            "calendar": self._calendar_context(await self._calendar_day(target_date), base_config),
            "daily_limits": self._limits(effective, plan),
            "current_plan": self._plan_data(plan, tz_name=tz_name),
            "next_item": next_item,
            "day_state": await self.plans.day_state(persona_id, target_date),
            "weather": await self._weather(persona_id),
            "recent_diff": await self.plans.revisions(plan["id"], effective["diff_revisions"], persona_id),
            "delivery_policy": {"quiet_now": quiet_now, "enforcement": "prompt_only",
                                "guidance": "当前为安静时段时仅输出 <msg/>。" if quiet_now else
                                            "只在确有调整价值时自然分享；否则输出 <msg/>。"}
        }
        host_tz = self.host_timezone_name()
        if host_tz is None or host_tz != tz_name:
            payload["timezone"] = tz_name
        payload = prepare_llm_payload(payload, tz_name, host_tz, drop=("source",))
        return "[KRD review context · request only]\n" + self._bounded(payload, effective["history_char_budget"])

    async def item_prompt(self, metadata: dict[str, Any]) -> str:
        persona_id = metadata["persona_id"]
        item = await self.store.one("SELECT * FROM items WHERE id=?", (metadata["item_id"],))
        item_id = item["id"] if item else ""
        if item is None:
            return "[KRD] The scheduled item no longer exists."
        from .plans import item_json
        item = item_json(item)
        plan = await self.plans.get_plan(item["plan_id"], persona_id)
        if plan is None:
            return "[KRD] The scheduled item no longer exists."
        base_config = await self.store.get_config(persona_id)
        matches = await self._active_day_types(persona_id, plan["date"])
        effective = await self.plans.effective_config(persona_id, matches[0]["id"] if matches else "")
        block = next((b for b in plan["blocks"] if b["id"] == item["block_id"]), None)
        tz_name = self.plans.policy.timezone_name(effective)
        state = await self.plans.day_state(persona_id, plan["date"])
        quiet_now = in_active_windows(
            effective["quiet_delivery_windows"], time.time(), self.plans.policy.timezone_name(effective))
        silence_requested = item["interaction"] == "silent" or quiet_now
        if silence_requested:
            guidance = "本次 effective_interaction=silent。安静完全由你的输出实现：只处理本日程时，仅输出 <msg/>，不要附加说明。"
        elif item["interaction"] == "must_message":
            guidance = "本次 effective_interaction=must_message。请产生有实际内容的可见回复，不要只输出 <msg/>。"
        else:
            guidance = "本次 effective_interaction=auto。可自然行动，也可保持安静；不要把机械确认当作发言。"
        recent = await self.plans.revisions(plan["id"], effective["diff_revisions"], persona_id)
        recent = [{"revision": row.get("revision"), "diff": row.get("diff", [])} for row in recent]
        for row in recent:
            for change in row.get("diff", []):
                change.pop("item_id", None)
        payload = {
            "instruction": base_config["execution_prompt"],
            "delivery_policy": {"scheduled_interaction": item["interaction"], "quiet_now": quiet_now,
                                "effective_interaction": "silent" if silence_requested else item["interaction"],
                                "enforcement": "prompt_only", "guidance": guidance},
            "day_types": self._day_types_text(matches),
            "day_type_prompt": await self._day_type_prompt(persona_id, matches, "execution"),
            "calendar": self._calendar_context(await self._calendar_day(plan["date"]), base_config),
            "daily_limits": self._limits(effective, plan),
            "day_state": state, "weather": await self._weather(persona_id),
            "plan": {key: plan[key] for key in ("date", "title", "overview", "planned_appearance", "planned_mood", "revision")},
            "current_item": {
                **{key: item[key] for key in ("title", "intent", "instruction", "target", "interaction",
                                              "execution_probability", "state", "schedule") if key in item},
                "id": self._short_item_id(item["id"]),
                **self._clock_fields(item.get("scheduled_at"), plan["date"], tz_name),
            },
            "siblings": [
                {"title": item["title"], **self._clock_fields(item.get("scheduled_at"), plan["date"], tz_name),
                 "state": item.get("state")}
                for item in (block.get("items", []) if block else [])
                if item.get("id") != item_id
            ],
            "recent_diff": recent
        }
        host_tz = self.host_timezone_name()
        if host_tz is None or host_tz != tz_name:
            payload["timezone"] = tz_name
        payload = prepare_llm_payload(payload, tz_name, host_tz, drop=("source",))
        return "[KRD item context · request only]\n" + self._bounded(payload, 10000)

    def _plan_data(self, plan: dict[str, Any] | None, include_instruction: bool = True,
                   tz_name: str = "Asia/Shanghai") -> dict[str, Any] | None:
        if plan is None:
            return None
        result = {key: plan[key] for key in (
            "date", "title", "overview", "planned_appearance", "planned_mood", "state", "revision")}
        result["blocks"] = []
        for block in plan["blocks"]:
            if block.get("meta", {}).get("archived"):
                continue
            items = []
            for item in block["items"]:
                view = {key: item[key] for key in (
                    "title", "intent", "instruction" if include_instruction else "title",
                    "schedule", "target", "interaction", "category", "execution_probability", "state") if key in item}
                view.update(self._clock_fields(item.get("scheduled_at"), plan["date"], tz_name))
                items.append(view)
            result["blocks"].append({"title": block["title"], "items": items})
        return result
