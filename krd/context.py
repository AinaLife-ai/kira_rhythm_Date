from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any

from .plans import PlanService
from .store import Store, dumps, loads
from .timeutils import in_active_windows, timezone
from .llm_format import prepare_llm_payload


class ContextBuilder:
    def __init__(self, store: Store, plans: PlanService, weather=None, host_timezone=None, threads=None):
        self.store = store
        self.plans = plans
        self.weather = weather
        self.calendar = None
        self.threads = threads
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
        items = [item for item in self._plan_items(plan) if item.get("state") not in {"cancelled", "deleted"}]
        return {
            "min_items": int(config["min_items"]),
            "max_items": int(config["max_items"]),
            "planned_items": len(items),
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
        schedule = ContextBuilder._item_schedule(item)
        if schedule.get("type") == "window":
            return day
        scheduled = item.get("scheduled_at")
        if scheduled:
            try:
                return datetime.fromtimestamp(float(scheduled), timezone(tz_name)).date().isoformat()
            except (TypeError, ValueError, OverflowError):
                return None
        return day

    @staticmethod
    def _item_schedule(item: dict[str, Any]) -> dict[str, Any]:
        schedule = item.get("schedule")
        if isinstance(schedule, dict):
            return schedule
        loaded = loads(item.get("schedule_json"), {})
        return loaded if isinstance(loaded, dict) else {}

    def _item_time_text(self, item: dict[str, Any], day: str, tz_name: str) -> str:
        schedule = self._item_schedule(item)
        if schedule.get("type") == "window":
            start = str(schedule.get("start", ""))[:8]
            end = str(schedule.get("end", ""))[:8]
            if start and end:
                return f"{start}-{end}"
        scheduled = item.get("scheduled_at")
        if scheduled:
            return self._clock_fields(scheduled, day, tz_name).get("at", "")
        at = str(schedule.get("at", "") or "")
        return at[:8]

    @staticmethod
    def _item_crosses_day(item: dict[str, Any]) -> bool:
        schedule = ContextBuilder._item_schedule(item)
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
        active_items = [item for item in items if item.get("state") not in {"cancelled", "deleted"}]
        done = sum(1 for item in active_items if item.get("state") in {"triggered", "triggered_silent"})
        lines = ["[KRD Agenda]"]
        if cross_day:
            lines.append(f"date: {day}")
        lines.extend((f"rev: {plan.get('revision', 0)}", f"progress: {done}/{len(active_items)}"))
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
        if weather.get("location"):
            lines.append(f"location: {weather['location']}")
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
        day = datetime.now(timezone(tz_name)).date().isoformat()
        state = await self.plans.day_state(persona_id, day)
        plan = await self.plans.get_plan_by_date(persona_id, day)
        matches = await self._active_day_types(persona_id, day)
        effective = await self.plans.effective_config(persona_id, matches[0]["id"] if matches else "")
        next_item = await self.store.one(
            "SELECT id,title,scheduled_at,target,schedule_json FROM items WHERE plan_id=? AND state='scheduled' ORDER BY scheduled_at LIMIT 1",
            (plan["id"],)) if plan else None
        calendar = self._calendar_context(await self._calendar_day(day), base_config)
        recent = await self.plans.recent_changes(persona_id, day, 1, meaningful_only=True)
        lines = ["[KRD DayState]"]
        if self._date_needs_display(tz_name):
            lines.extend((f"date: {day}", f"timezone: {tz_name}"))
        day_types = self._day_types_text(matches) or "none"
        lines.append(f"day_types: {day_types}")
        for key in ("appearance", "mood", "location", "activity", "note"):
            value = state.get(f"current_{key}")
            if value:
                lines.append(f"{key}: {value}")
        limits = self._limits(effective, plan)
        lines.append(f"daily_limits: {limits['min_items']}–{limits['max_items']} items, planned {limits['planned_items']}")
        if next_item:
            next_bits = [str(next_item.get("title") or ""), self._item_time_text(next_item, day, tz_name)]
            next_day = self._item_date(next_item, day, tz_name)
            if next_day and next_day != day:
                next_bits.insert(1, next_day)
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
        agenda_text = ""
        if base_config.get("inject_agenda", True):
            agenda_limit = int(base_config.get("agenda_max_chars", 2400))
            agenda_text = self._bounded(self._agenda_text(plan, day, tz_name, current_sid), agenda_limit)
        try:
            thread_text = await self.threads.chat_block(persona_id, base_config) if self.threads else ""
        except Exception:
            thread_text = ""
        return (self._bounded("\n".join(lines), 1400)
                + ("\n\n" + thread_text if thread_text else "")
                + ("\n\n" + weather_text if weather_text else "")
                + (("\n\n" + agenda_text) if agenda_text else ""))

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
        full_days = max(0, int(base_config.get("history_days", 3)))
        digest_days = max(0, int(base_config.get("history_digest_days", 4)))
        full_start = (datetime.fromisoformat(target_date) - timedelta(days=full_days)).date().isoformat()
        full_end = (datetime.fromisoformat(target_date) - timedelta(days=1)).date().isoformat()
        digest_start = (datetime.fromisoformat(full_start) - timedelta(days=digest_days)).date().isoformat()
        digest_end = (datetime.fromisoformat(full_start) - timedelta(days=1)).date().isoformat()
        full_plans = await self.plans.list_plans(persona_id, full_start, full_end) if full_days else []
        digest_plans = await self.plans.list_plans(persona_id, digest_start, digest_end) if digest_days else []
        recent_full = [
            self._plan_data(plan, include_instruction=bool(base_config.get("history_include_instruction", True)),
                            tz_name=tz_name,
                            instruction_chars=int(base_config.get("history_instruction_chars", 200)))
            for plan in full_plans
        ]
        recent_digest = [self._plan_digest(plan) for plan in digest_plans]
        matches = await self._active_day_types(persona_id, target_date)
        effective = await self.plans.effective_config(persona_id, matches[0]["id"] if matches else "")
        calendar = self._calendar_context(await self._calendar_day(target_date), base_config)
        weather = await self._weather(persona_id, target_date, "plan")
        outcomes_days = max(0, int(base_config.get("recent_outcomes_days", 2)))
        unfinished_days = max(0, int(base_config.get("unfinished_days", 3)))
        future_days = max(0, int(base_config.get("future_plan_days", 2)))
        recent_outcomes = await self._recent_outcomes(persona_id, target_date, outcomes_days, tz_name)
        unfinished = await self._unfinished(persona_id, target_date, unfinished_days)
        future_plans = await self.plans.list_plans(
            persona_id, (datetime.fromisoformat(target_date) + timedelta(days=1)).date().isoformat(),
            (datetime.fromisoformat(target_date) + timedelta(days=future_days)).date().isoformat()
        ) if future_days else []
        future_payload = [
            {"date": plan["date"], "title": plan["title"],
             "items": [item.get("title", "") for block in plan.get("blocks", [])
                       for item in block.get("items", []) if item.get("state") not in {"deleted", "cancelled"}]}
            for plan in future_plans
        ]
        threads_enabled = bool(base_config.get("threads", {}).get("enabled", True))
        run_id = str(metadata.get("run_id", "") or "")
        try:
            thread_payload = (await self.threads.planning_payload(persona_id, run_id=run_id)
                              if self.threads else
                              {"required": False, "threads": [], "more": 0, "contract": ""})
        except Exception:
            thread_payload = {"required": False, "threads": [], "more": 0, "contract": ""}
        try:
            unanswered = await self.threads.unanswered(persona_id) \
                if self.threads and thread_payload.get("required") else []
        except Exception:
            unanswered = []
        instruction = base_config["planning_prompt"]
        if not thread_payload.get("required"):
            if not threads_enabled:
                instruction += "\n[KRD 目标层] 本次未启用目标/约定；忽略 threads_requiring_response / threads_reference 与 thread_* 操作。"
            else:
                instruction += "\n[KRD 目标层] 本次没有必须回应的目标；若上下文出现 threads_reference，仅作参考，不需要 thread_response。"
        pattern = await self._recent_pattern(persona_id, target_date, max(1, full_days or digest_days or 3))
        payload = {
            "instruction": instruction + (("\n" + self._weather_rule()) if weather else ""),
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
            "recent_plans": {"full": recent_full, "digest": recent_digest},
            "recent_outcomes": recent_outcomes,
            "unfinished": unfinished,
            "future_plans": future_payload,
            "recent_changes": self._compact_changes(
                await self.plans.recent_changes(persona_id, target_date, 2, meaningful_only=True)),
            "recent_pattern": pattern,
            "weather": weather
        }
        if thread_payload.get("threads"):
            required_rows = [row for row in thread_payload["threads"] if row.get("response_required")]
            optional_rows = [row for row in thread_payload["threads"] if not row.get("response_required")]
            if thread_payload.get("required") and required_rows:
                payload["threads_requiring_response"] = required_rows
                if optional_rows:
                    payload["threads_reference"] = optional_rows
                    payload["threads_note"] = "threads_reference 仅供补充参考，不要求回应；只回应 threads_requiring_response。"
                if thread_payload.get("more"):
                    payload["threads_more"] = thread_payload["more"]
                payload["response_contract"] = thread_payload.get("contract", "")
            else:
                payload["threads_reference"] = thread_payload["threads"]
                if thread_payload.get("more"):
                    payload["threads_more"] = thread_payload["more"]
                payload["threads_note"] = "目标/约定仅供参考；可按需推进或打卡，未回应不会阻断本次规划。"
        if unanswered and thread_payload.get("required"):
            payload["unanswered_threads"] = unanswered
        try:
            untouched = await self.threads.untouched(
                persona_id, max(1, int(base_config.get("unfinished_days", 3)))) \
                if self.threads and threads_enabled else []
        except Exception:
            untouched = []
        if untouched:
            payload["thread_untouched"] = untouched
        today = await self.plans.current_date(persona_id)
        if today != target_date:
            payload["today_changes"] = self._compact_changes(
                await self.plans.recent_changes(persona_id, today, 2, meaningful_only=True))
        host_tz = self.host_timezone_name()
        if host_tz is None or host_tz != tz_name:
            payload["timezone"] = tz_name
        payload = prepare_llm_payload(payload, tz_name, host_tz, drop=("source",))
        return "[KRD planning context · request only]\n" + self._fit_payload(
            payload, int(base_config.get("history_char_budget", 16000)))

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
        review_instruction = effective["planning_review"]["prompt"]
        if not base_config.get("threads", {}).get("enabled", True):
            review_instruction += "\n[KRD 目标层] 本次未启用目标/约定；忽略目标/约定相关提示。"
        payload = {
            "instruction": review_instruction + (("\n" + self._weather_rule()) if weather else ""),
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
            "threads": await self._review_threads(persona_id, effective),
            "unanswered_threads": await self._unanswered_threads(persona_id, effective),
            "delivery_policy": {"quiet_now": quiet_now, "enforcement": "prompt_only",
                                "guidance": "当前为安静时段时仍可调用工具，但最终仅输出 <msg/>，不要附加说明。" if quiet_now else
                                            "只在确有调整价值时自然分享；否则可调用工具，但最终仅输出 <msg/>。"}
        }
        host_tz = self.host_timezone_name()
        if host_tz is None or host_tz != tz_name:
            payload["timezone"] = tz_name
        payload = prepare_llm_payload(payload, tz_name, host_tz, drop=("source",))
        return "[KRD review context · request only]\n" + self._fit_payload(payload, int(effective["history_char_budget"]))

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
            guidance = "本次 effective_interaction=silent。安静完全由你的输出实现：只处理本日程时，可调用工具但仅输出 <msg/>，不要附加说明。"
        elif item["interaction"] == "must_message":
            guidance = "本次 effective_interaction=must_message。请产生有实际内容的可见回复，不要只输出 <msg/>。"
        else:
            guidance = "本次 effective_interaction=auto。可自然行动，也可保持安静；不要把机械确认当作发言。"
        recent = await self.plans.revisions(plan["id"], effective["diff_revisions"], persona_id)
        recent = [{"revision": row.get("revision"), "diff": row.get("diff", [])} for row in recent]
        for row in recent:
            for change in row.get("diff", []):
                change.pop("item_id", None)
        execution_instruction = base_config["execution_prompt"]
        if not base_config.get("threads", {}).get("enabled", True):
            execution_instruction += "\n[KRD 目标层] 本次未启用目标/约定；忽略 thread_touch / thread_add 等目标操作。"
        item_thread = await self._item_thread(persona_id, item.get("thread_id", ""), effective)
        if item_thread and item_thread.get("status") not in {"open", "paused"}:
            execution_instruction += "\n[KRD 目标层] 当前小项关联的目标已结束；它只作历史参考，不要用 thread_touch 追加打卡。"
        payload = {
            "instruction": execution_instruction,
            "delivery_policy": {"scheduled_interaction": item["interaction"], "quiet_now": quiet_now,
                                "effective_interaction": "silent" if silence_requested else item["interaction"],
                                "enforcement": "prompt_only", "guidance": guidance},
            "day_types": self._day_types_text(matches),
            "day_type_prompt": await self._day_type_prompt(persona_id, matches, "execution"),
            "calendar": self._calendar_context(await self._calendar_day(plan["date"]), base_config),
            "daily_limits": self._limits(effective, plan),
            "day_state": state, "weather": await self._weather(persona_id, plan["date"], "item"),
            "day_so_far": await self._day_so_far(persona_id, plan),
            "thread": item_thread,
            "plan": {key: plan[key] for key in ("date", "title", "overview", "planned_appearance", "planned_mood", "revision")},
            "current_item": {
                **{key: item[key] for key in ("title", "intent", "instruction", "target", "interaction",
                                              "execution_probability", "state", "schedule", "thread_id") if key in item},
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
        return "[KRD item context · request only]\n" + self._fit_payload(payload, 10000)

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

    async def _review_threads(self, persona_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.threads or not config.get("threads", {}).get("enabled", True):
            return []
        try:
            return await self.threads.review_payload(persona_id, config)
        except Exception:
            return []

    async def _unanswered_threads(self, persona_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.threads or not config.get("threads", {}).get("enabled", True):
            return []
        try:
            return await self.threads.unanswered(persona_id)
        except Exception:
            return []

    async def _item_thread(self, persona_id: str, thread_id: str, config: dict[str, Any]) -> dict[str, Any] | None:
        if not self.threads or not thread_id or not config.get("threads", {}).get("enabled", True):
            return None
        try:
            return await self.threads.execution_payload(persona_id, thread_id, config)
        except Exception:
            return None

    async def _day_so_far(self, persona_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        done = [item.get("title", "") for block in plan.get("blocks", []) for item in block.get("items", [])
                if item.get("state") in {"triggered", "triggered_silent"}]
        experiences = await self.store.all(
            "SELECT content,kind FROM experiences WHERE persona_id=? AND date=? "
            "ORDER BY created_at DESC LIMIT 2", (persona_id, plan.get("date", "")))
        return {
            "done": done[-6:],
            "experiences": [" ".join(str(row.get("content") or "").split())[:80] for row in experiences],
        }

    def _plan_data(self, plan: dict[str, Any] | None, include_instruction: bool = True,
                   tz_name: str = "Asia/Shanghai", instruction_chars: int = 200) -> dict[str, Any] | None:
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
                if item.get("state") == "deleted":
                    continue
                view = {key: item[key] for key in (
                    "title", "intent", "schedule", "target", "interaction", "category",
                    "execution_probability", "state") if key in item}
                if include_instruction:
                    view["instruction"] = str(item.get("instruction") or "")[:instruction_chars]
                if item.get("thread_id"):
                    view["thread_id"] = item["thread_id"]
                if item.get("reason"):
                    view["reason"] = item["reason"]
                view["id"] = self._short_item_id(item.get("id", ""))
                view.update(self._clock_fields(item.get("scheduled_at"), plan["date"], tz_name))
                items.append(view)
            result["blocks"].append({"title": block["title"], "items": items})
        return result

    @staticmethod
    def _plan_digest(plan: dict[str, Any]) -> dict[str, Any]:
        items = [item for block in plan.get("blocks", []) for item in block.get("items", [])
                 if item.get("state") not in {"deleted", "cancelled"}]
        states = [item.get("state", "scheduled") for block in plan.get("blocks", [])
                  for item in block.get("items", [])]
        return {
            "date": plan.get("date"),
            "title": plan.get("title", ""),
            "items": len(items),
            "done": sum(1 for state in states if state in {"triggered", "triggered_silent"}),
            "missed": sum(1 for state in states if state == "missed"),
            "cancelled": sum(1 for state in states if state == "cancelled"),
            "threads": sum(1 for item in items if item.get("thread_id")),
            "note": str(plan.get("overview") or "")[:80],
        }

    async def _recent_outcomes(self, persona_id: str, target_date: str, days: int,
                               tz_name: str) -> list[dict[str, Any]]:
        if days <= 0:
            return []
        end = (datetime.fromisoformat(target_date) - timedelta(days=1)).date().isoformat()
        start = (datetime.fromisoformat(end) - timedelta(days=days - 1)).date().isoformat()
        plans = await self.plans.list_plans(persona_id, start, end)
        by_date: dict[str, dict[str, Any]] = {}
        for plan in plans:
            digest = self._plan_digest(plan)
            by_date[plan["date"]] = {**digest, "notes": []}
        experiences = await self.store.all(
            "SELECT date,content,kind FROM experiences WHERE persona_id=? AND date BETWEEN ? AND ? "
            "ORDER BY created_at DESC", (persona_id, start, end))
        for row in experiences:
            bucket = by_date.setdefault(row["date"], {"date": row["date"], "notes": []})
            note = " ".join(str(row.get("content") or "").split())[:80]
            if note and note not in bucket["notes"] and len(bucket["notes"]) < 3:
                bucket["notes"].append(note)
        runs = await self.store.all(
            "SELECT p.date AS date,i.title AS title,r.raw_output AS text FROM runs r "
            "JOIN items i ON i.id=r.item_id JOIN plans p ON p.id=i.plan_id "
            "WHERE p.persona_id=? AND p.date BETWEEN ? AND ? AND r.responded_at IS NOT NULL "
            "ORDER BY r.responded_at DESC LIMIT 100", (persona_id, start, end))
        for row in runs:
            bucket = by_date.setdefault(row["date"], {"date": row["date"], "notes": []})
            text = re.sub(r"<[^>]+>", " ", str(row.get("text") or ""))
            note = " ".join(text.split())[:60]
            if note and note not in bucket["notes"] and len(bucket["notes"]) < 3:
                bucket["notes"].append(note)
        return [by_date[key] for key in sorted(by_date, reverse=True)]

    async def _unfinished(self, persona_id: str, target_date: str, days: int) -> list[dict[str, Any]]:
        if days <= 0:
            return []
        end = (datetime.fromisoformat(target_date) - timedelta(days=1)).date().isoformat()
        start = (datetime.fromisoformat(end) - timedelta(days=days - 1)).date().isoformat()
        result = []
        for plan in await self.plans.list_plans(persona_id, start, end):
            for block in plan.get("blocks", []):
                for item in block.get("items", []):
                    if item.get("state") in {"missed", "cancelled"}:
                        result.append({"date": plan["date"], "title": item.get("title", ""),
                                       "reason": item.get("reason", ""), "state": item.get("state")})
        return result[-20:]

    async def _recent_pattern(self, persona_id: str, target_date: str, days: int) -> dict[str, Any]:
        end = (datetime.fromisoformat(target_date) - timedelta(days=1)).date().isoformat()
        start = (datetime.fromisoformat(end) - timedelta(days=max(0, days - 1))).date().isoformat()
        plans = await self.plans.list_plans(persona_id, start, end) if days > 0 else []
        counts = []
        title_days: dict[str, set[str]] = {}
        for plan in plans:
            items = [item for block in plan.get("blocks", []) for item in block.get("items", [])
                     if item.get("state") not in {"cancelled", "deleted"}]
            counts.append(len(items))
            for item in items:
                title = re.sub(r"[\s，。！？、,.!?·…—\-]", "", str(item.get("title") or ""))
                if title:
                    title_days.setdefault(title, set()).add(plan["date"])
        repeated = [title for title, dates in sorted(title_days.items(), key=lambda pair: (-len(pair[1]), pair[0]))
                    if len(dates) >= 2][:5]
        if not plans:
            note = "还没有足够的历史。"
        elif repeated or (counts and len(set(counts)) == 1):
            note = f"最近 {len(plans)} 天结构接近；如果今天仍然这样，请在 overview 里说明原因。"
        else:
            note = f"最近 {len(plans)} 天有变化；继续保持依据现场。"
        return {"days": len(plans), "counts": counts, "repeated_titles": repeated, "note": note}

    @staticmethod
    def _fit_payload(payload: dict[str, Any], limit: int) -> str:
        """Shrink structured context without ever cutting JSON mid-string."""
        def text() -> str:
            return dumps(payload)

        if len(text()) <= limit:
            return text()

        def trim_full() -> bool:
            plans = (payload.get("recent_plans") or {}).get("full")
            if isinstance(plans, list) and plans:
                plans.pop(0)
                payload["truncated"] = True
                return True
            return False

        def trim_diff() -> bool:
            diff = payload.get("recent_diff")
            if isinstance(diff, list) and diff:
                diff.pop(0)
                payload["truncated"] = True
                return True
            return False

        def trim_siblings() -> bool:
            siblings = payload.get("siblings")
            if isinstance(siblings, list) and siblings:
                siblings.pop()
                payload["truncated"] = True
                return True
            return False

        def trim_item_thread() -> bool:
            thread = payload.get("thread")
            if not isinstance(thread, dict):
                return False
            logs = thread.get("logs")
            if isinstance(logs, list) and logs:
                thread["logs"] = []
                payload["truncated"] = True
                return True
            dossier = str(thread.get("dossier") or "")
            if len(dossier) > 301:
                thread["dossier"] = dossier[:300] + "…"
                payload["truncated"] = True
                return True
            return False

        def trim_threads() -> bool:
            # Required threads are a hard contract: never remove a row from
            # threads_requiring_response just to satisfy the byte budget. The
            # scheduler persists the same ids and would otherwise wait forever
            # for responses that the model can no longer see.
            required_key = "threads_requiring_response"
            if isinstance(payload.get(required_key), list) and payload[required_key]:
                threads = payload[required_key]
                for thread in reversed(threads):
                    dossier = str(thread.get("dossier") or "")
                    if len(dossier) > 301:
                        thread["dossier"] = dossier[:300] + "…"
                        payload["truncated"] = True
                        return True
                for thread in reversed(threads):
                    logs = thread.get("logs")
                    if isinstance(logs, list) and logs:
                        thread["logs"] = []
                        payload["truncated"] = True
                        return True
                # Last resort: keep every required id, but reduce each entry to
                # the fields needed to make a response decision.
                changed = False
                compact_keys = ("id", "short_id", "kind", "title", "status", "priority",
                                "next_step", "due_at", "due", "due_in_days", "overdue",
                                "dossier", "response_required")
                for thread in threads:
                    if any(key not in thread for key in ("id", "response_required")):
                        continue
                    source = {key: thread.get(key) for key in compact_keys if key in thread}
                    source["dossier"] = str(thread.get("dossier") or "")[:160]
                    source.setdefault("response_required", True)
                    if source != thread:
                        thread.clear()
                        thread.update(source)
                        changed = True
                if changed:
                    payload["truncated"] = True
                    return True
                return False
            reference_key = "threads_reference"
            threads = payload.get(reference_key)
            if not isinstance(threads, list) or not threads:
                return False
            for thread in reversed(threads):
                dossier = str(thread.get("dossier") or "")
                if len(dossier) > 301:
                    thread["dossier"] = dossier[:300] + "…"
                    payload["truncated"] = True
                    return True
            for thread in reversed(threads):
                logs = thread.get("logs")
                if isinstance(logs, list) and len(logs) > 1:
                    logs.pop()
                    payload["truncated"] = True
                    return True
            if len(threads) > 3:
                payload["threads_more"] = int(payload.get("threads_more", 0)) + 1
                payload[reference_key] = threads[:-1]
                payload["truncated"] = True
                return True
            return False

        def trim_outcomes() -> bool:
            outcomes = payload.get("recent_outcomes")
            if isinstance(outcomes, list) and outcomes:
                outcomes.pop()
                payload["truncated"] = True
                return True
            return False

        def trim_unfinished() -> bool:
            unfinished = payload.get("unfinished")
            if isinstance(unfinished, list) and unfinished:
                unfinished.pop()
                payload["truncated"] = True
                return True
            return False

        def trim_future() -> bool:
            future = payload.get("future_plans")
            if isinstance(future, list) and future:
                future.pop()
                payload["truncated"] = True
                return True
            return False

        def trim_digest() -> bool:
            plans = (payload.get("recent_plans") or {}).get("digest")
            if isinstance(plans, list) and plans:
                plans.pop(0)
                payload["truncated"] = True
                return True
            return False

        reducers = [trim_diff, trim_siblings, trim_item_thread, trim_digest, trim_outcomes,
                    trim_unfinished, trim_future, trim_full, trim_threads]
        for reducer in reducers:
            while reducer():
                if len(text()) <= limit:
                    return text()
        for key in ("recent_pattern", "weather", "recent_changes", "today_changes", "future_plans",
                    "unfinished", "recent_outcomes", "recent_diff", "siblings",
                    "thread_untouched", "unanswered_threads"):
            if key in payload:
                payload.pop(key, None)
                payload["truncated"] = True
                if len(text()) <= limit:
                    return text()
        minimal = {
            "instruction": str(payload.get("instruction", ""))[:20000],
            "focus": payload.get("focus", {}),
            "truncated": True,
            "note": "上下文超出预算；请用 rhythm_view 查看完整计划、目标或历史。",
        }
        # Keep the context the model needs to act or review coherently. The
        # budget is soft at this last resort: losing current_plan/next_item/
        # constraints would make an otherwise valid turn blind, so these
        # critical fields survive even when the soft budget is exceeded.
        for key in ("current_item", "current_plan", "next_item", "delivery_policy", "plan",
                    "daily_limits", "constraints", "calendar", "thread", "day_so_far"):
            if key in payload:
                minimal[key] = payload[key]
        # The response contract must survive any budget reduction. Dropping it
        # while the run still requires those ids creates an impossible planning
        # turn, so keep the compact required set even if the soft budget is
        # exceeded.
        for key in ("threads_requiring_response", "threads_more", "response_contract"):
            if key in payload:
                minimal[key] = payload[key]
        return dumps(minimal)
