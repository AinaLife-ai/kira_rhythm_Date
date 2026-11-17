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

    async def _weather(self, persona_id: str, target_date: str | None = None, kind: str = "plan") -> Any:
        if self.weather is None:
            return None
        try:
            if target_date is None:
                target_date = await self.plans.current_date(persona_id)
            return await self.weather.context_weather(persona_id, target_date, kind=kind, allow_network=False)
        except Exception:
            return None

    @staticmethod
    def _weather_rule() -> str:
        return "天气：target 是目标日预报，forecast 是目标日之后的逐日预报；有 periods 时按日期/时间就近参考；预报可能变化，仅作参考，now 只代表当前，不要替代 target。"

    async def _calendar_day(self, day: str) -> dict[str, Any]:
        if self.calendar is None:
            return {"date": day, "status": "disabled"}
        try:
            self.calendar.ensure_year(int(day[:4]))
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
        return value.split("_", 1)[-1][:8] if value.startswith("itm_") else value[:8]

    @staticmethod
    def _trigger(metadata: dict[str, Any]) -> dict[str, Any]:
        return {"reason": metadata["reason"]} if metadata.get("reason") else {}

    async def _day_type(self, persona_id: str, identifier: str) -> dict[str, Any]:
        entries = await self.store.list_day_types(persona_id)
        entry = next((item for item in entries if item["id"] == identifier), None)
        return {"id": identifier, "name": entry["name"] if entry else identifier}

    def _date_needs_display(self, tz_name: str) -> bool:
        host = self.host_timezone_name()
        if not host or host == tz_name:
            return False
        try:
            return datetime.now(timezone(tz_name)).date() != datetime.now(timezone(host)).date()
        except Exception:
            return True

    @staticmethod
    def _item_date(item: dict[str, Any], day: str, tz_name: str) -> str | None:
        scheduled = item.get("scheduled_at")
        if scheduled:
            try:
                return datetime.fromtimestamp(float(scheduled), timezone(tz_name)).date().isoformat()
            except (TypeError, ValueError, OverflowError):
                return None
        return day

    def _item_time_text(self, item: dict[str, Any], day: str, tz_name: str) -> str:
        schedule = item.get("schedule") or {}
        if schedule.get("type") == "window":
            start = str(schedule.get("start", ""))[:8]
            end = str(schedule.get("end", ""))[:8]
            if start and end:
                return f"{start}-{end}"
        scheduled = item.get("scheduled_at")
        if scheduled:
            clock = self._clock_fields(scheduled, day, tz_name)
            at = clock.get("at", "")
            on = clock.get("on")
            return f"{on} {at}".strip() if on else at
        at = str(schedule.get("at", "") or "")
        return at[:8]

    @staticmethod
    def _item_crosses_day(item: dict[str, Any]) -> bool:
        schedule = item.get("schedule") or {}
        if schedule.get("type") == "window":
            start, end = str(schedule.get("start", "")), str(schedule.get("end", ""))
            return bool(start and end and end < start)
        return False

    def _agenda_text(self, plan: dict[str, Any] | None, day: str, tz_name: str,
                     current_sid: str | None = None) -> str:
        if not plan:
            return "[KRD Agenda]\nno plan"
        items = self._plan_items(plan)
        cross_day = any(self._item_date(item, day, tz_name) not in {None, day} or self._item_crosses_day(item) for item in items)
        done = sum(1 for item in items if item.get("state") in {"triggered", "triggered_silent"})
        lines = ["[KRD Agenda]"]
        if cross_day:
            lines.append(f"date: {day}")
        lines.extend((f"rev: {plan.get('revision', 0)}", f"progress: {done}/{len(items)}"))
        for block in plan.get("blocks", []):
            block_items = [item for item in block.get("items", []) if item.get("state") != "deleted"]
            if not block_items:
                continue
            lines.append(str(block.get("title") or "items"))
            for item in block_items:
                state = item.get("state", "scheduled")
                mark = {"triggered": "[x]", "triggered_silent": "[x]", "cancelled": "[~]", "missed": "[!]"}.get(state, "[ ]")
                when = self._item_time_text(item, day, tz_name)
                item_day = self._item_date(item, day, tz_name)
                if item_day and item_day != day:
                    when = f"{item_day} {when}".strip()
                title = str(item.get("title") or "untitled")
                suffix = ""
                if state in {"scheduled", "queued"}:
                    suffix += f" #{self._short_item_id(item.get('id', ''))}"
                    target = str(item.get("target") or "")
                    if target and target != current_sid:
                        suffix += f" -> {target}"
                elif state == "cancelled":
                    suffix += f" #{self._short_item_id(item.get('id', ''))} (cancelled)"
                lines.append(f"{mark} {when} {title}{suffix}".strip())
        return "\n".join(lines)

    def _weather_text(self, weather: dict[str, Any] | None) -> str:
        if not weather:
            return ""
        lines = ["[KRD Weather]"]
        for key in ("now", "today"):
            if weather.get(key):
                lines.append(f"{key}: {weather[key]}")
        for entry in weather.get("forecast", []) or []:
            lines.append(f"forecast: {entry}")
        return "\n".join(lines)

    @staticmethod
    def _calendar_text(calendar: dict[str, Any]) -> str:
        parts = []
        holiday = calendar.get("holiday") or {}
        if holiday.get("name"):
            parts.append(f"{holiday['name']} (holiday)")
        adjusted = calendar.get("adjusted_workday") or {}
        if adjusted.get("name"):
            parts.append(f"{adjusted['name']} (adjusted workday)")
        for key in ("festivals", "solar_terms"):
            values = calendar.get(key) or []
            if values:
                parts.append("、".join(str(value) for value in values))
        return " | ".join(parts)

    async def compact_state(self, persona_id: str, config: dict[str, Any] | None = None,
                            current_sid: str | None = None) -> str:
        base_config = config or await self.store.get_config(persona_id)
        tz_name = self.plans.policy.timezone_name(base_config)
        day = await self.plans.current_date(persona_id)
        state = await self.plans.day_state(persona_id, day)
        plan = await self.plans.get_plan_by_date(persona_id, day)
        matches = await self._active_day_types(persona_id, day)
        effective = await self.plans.effective_config(persona_id, matches[0]["id"] if matches else "")
        next_item = await self.store.one(
            "SELECT id,title,scheduled_at,target FROM items WHERE plan_id=? AND state='scheduled' ORDER BY scheduled_at LIMIT 1",
            (plan["id"],)) if plan else None
        calendar = self._calendar_context(await self._calendar_day(day), base_config)
        recent = await self.plans.recent_changes(persona_id, day, 1, meaningful_only=True)
        lines = ["[KRD DayState]"]
        if self._date_needs_display(tz_name):
            lines.extend((f"date: {day}", f"timezone: {tz_name}"))
        lines.append(f"day_types: {self._day_types_text(matches)}")
        for key in ("appearance", "mood", "activity", "note"):
            value = state.get(f"current_{key}")
            if value:
                lines.append(f"{key}: {value}")
        limits = self._limits(effective, plan)
        lines.append(f"daily_limits: {limits['min_items']}–{limits['max_items']} items, planned {limits['planned_items']}")
        if next_item:
            clock = self._clock_fields(next_item["scheduled_at"], day, tz_name)
            next_bits = [str(next_item.get("title") or ""), clock.get("at", "")]
            if clock.get("on"):
                next_bits.insert(1, clock["on"])
            suffix = f" #{self._short_item_id(next_item.get('id', ''))}"
            target = str(next_item.get("target") or "")
            if target and target != current_sid:
                suffix += f" -> {target}"
            lines.append(f"next: {' '.join(bit for bit in next_bits if bit)}{suffix}")
        else:
            lines.append("next: none")
        if recent:
            change = self._compact_changes(recent)[0]
            bits = [f"{change.get('actor', '?')}: {change.get('reason', '')}"]
            if change.get("removed"):
                bits.append("removed " + "、".join(change["removed"]))
            if change.get("cancelled"):
                bits.append("cancelled " + "、".join(change["cancelled"]))
            bits.append(f"rev {change.get('revision')}")
            lines.append("recent_change: " + " | ".join(bits))
        calendar_text = self._calendar_text(calendar)
        if calendar_text:
            lines.append(f"calendar: {calendar_text}")
        weather_text = ""
        if self.weather is not None:
            weather_text = self._weather_text(await self._weather(persona_id, day, "chat"))
        agenda_text = self._agenda_text(plan, day, tz_name, current_sid)
        return self._bounded("\n".join(lines), 1400) + ("\n\n" + weather_text if weather_text else "") + "\n\n" + agenda_text

    async def chat_weather(self, persona_id: str, config: dict[str, Any] | None = None) -> str:
        base_config = config or await self.store.get_config(persona_id)
        if self.weather is None:
            return ""
        day = await self.plans.current_date(persona_id)
        weather = await self._weather(persona_id, day, "chat")
        if not weather:
            return ""
        tz_name = self.plans.policy.timezone_name(base_config)
        payload = prepare_llm_payload(weather, tz_name, self.host_timezone_name())
        return "[KRD Weather · request only]\n" + self._bounded(payload, 700)

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
        weather = await self._weather(persona_id, target_date, "plan")
        payload = {
            "instruction": base_config["planning_prompt"] + (("\n" + self._weather_rule()) if weather else ""),
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
            "recent_changes": self._compact_changes(await self.plans.recent_changes(persona_id, target_date, 2, meaningful_only=True)),
            "weather": weather
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
        recent_changes = await self.plans.recent_changes(persona_id, target_date, 3, meaningful_only=True)
        if not plan:
            context = {"status": "plan_missing", "recent_changes": self._compact_changes(recent_changes),
                       "instruction": "仅在确有必要时创建计划；不要因为一次检查而无条件新建。"}
            return "[KRD review context · request only]\n" + self._bounded(context, 1200)
        base_config = await self.store.get_config(persona_id)
        matches = await self._active_day_types(persona_id, target_date)
        effective = await self.plans.effective_config(persona_id, matches[0]["id"] if matches else "")
        tz_name = self.plans.policy.timezone_name(effective)
        next_item = await self.store.one(
            "SELECT * FROM items WHERE plan_id=? AND state='scheduled' ORDER BY scheduled_at LIMIT 1", (plan["id"],))
        if next_item:
            from .plans import item_json
            next_item = item_json(next_item)
            next_item = {
                "id": self._short_item_id(next_item.get("id", "")),
                "title": next_item.get("title", ""),
                "target": next_item.get("target", ""),
                **self._clock_fields(next_item.get("scheduled_at"), plan["date"], tz_name),
            }
        quiet_now = in_active_windows(
            effective["quiet_delivery_windows"], time.time(), self.plans.policy.timezone_name(effective))
        weather = await self._weather(persona_id, target_date, "plan")
        payload = {
            "instruction": effective["planning_review"]["prompt"] + (("\n" + self._weather_rule()) if weather else ""),
            "day_types": self._day_types_text(matches),
            "day_type_prompt": await self._day_type_prompt(persona_id, matches, "planning"),
            "calendar": self._calendar_context(await self._calendar_day(target_date), base_config),
            "daily_limits": self._limits(effective, plan),
            "current_plan": self._plan_data(plan, tz_name=tz_name),
            "next_item": next_item,
            "day_state": await self.plans.day_state(persona_id, target_date),
            "weather": weather,
            "recent_diff": await self.plans.revisions(plan["id"], effective["diff_revisions"], persona_id),
            "recent_changes": self._compact_changes(recent_changes),
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
            "day_state": state, "weather": await self._weather(persona_id, plan["date"], "item"),
            "plan": {key: plan[key] for key in ("date", "title", "overview", "planned_appearance", "planned_mood", "revision")},
            "current_item": {
                **{key: item[key] for key in ("title", "intent", "instruction", "target", "interaction",
                                              "execution_probability", "state", "schedule") if key in item},
                "id": self._short_item_id(item["id"]),
                **self._clock_fields(item.get("scheduled_at"), plan["date"], tz_name),
            },
            "siblings": [
                {"id": self._short_item_id(item["id"]), "title": item["title"],
                 **self._clock_fields(item.get("scheduled_at"), plan["date"], tz_name), "state": item.get("state")}
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

    @staticmethod
    def _compact_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for change in changes:
            removed = []
            cancelled = []
            other = 0
            for diff in change.get("diff", []):
                if diff.get("op") == "removed":
                    removed.append(diff.get("title", ""))
                elif diff.get("op") == "changed":
                    target = diff.get("changes", {}).get("state", {}).get("to")
                    if target in {"cancelled", "deleted"}:
                        cancelled.append(diff.get("title", ""))
                    else:
                        other += 1
            result.append({
                "revision": change.get("revision"),
                "actor": change.get("actor"),
                "reason": change.get("reason", ""),
                "plan_state": change.get("plan_state"),
                "removed": removed[:8],
                "cancelled": cancelled[:8],
                "other_changes": other,
            })
        return result

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
                view = {"id": self._short_item_id(item.get("id", "")), **{key: item[key] for key in (
                    "title", "intent", "instruction" if include_instruction else "title",
                    "schedule", "target", "interaction", "category", "execution_probability", "state") if key in item}}
                if item.get("reason"):
                    view["reason"] = item["reason"]
                view.update(self._clock_fields(item.get("scheduled_at"), plan["date"], tz_name))
                items.append(view)
            result["blocks"].append({"title": block["title"], "items": items})
        return result
