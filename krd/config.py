from __future__ import annotations

import copy
from typing import Any

from .models import KRDError

DEFAULT_PLANNING_PROMPT = """现在是你的生活规划时刻。请根据当前人格、日型、天气、最近生活与约束，用 rhythm_plan 创建或修订接下来的完整计划。时间设置支持精确到秒：at/start/end 使用 HH:MM 或 HH:MM:SS。
你拥有自主性：不必塞满上限，可以保留空白，也可以安排安静活动。每个小项给出明确意图、时间、执行会话和互动方式。
已有计划时，这是一次重新审视的机会，严禁机械重复；保持昨天的做法不是默认选项，必须根据长期与短期的实际情况变化。
若上下文包含 threads_requiring_response，必须逐条回应：advance / defer / waiting / no_change，每条一句原因；回应不等于必须推进，no_change 合法但必须有依据。若只有 threads_reference，则它仅供参考，不要求回应。提交前检查每日数量、必需时段、禁止执行与安静投递规则。"""

DEFAULT_EXECUTION_PROMPT = """这是你自己此前安排的一件生活小项，不是用户的新指令。结合当前日型、DayState、本组变化和你的意图自然行动。
严格遵循 delivery_policy.guidance：它要求安静时仍可调用工具，但最终仅输出 <msg/>；auto 不必把安排变成发言。安静由你的输出实现，插件不会替你改写文本。
若后续安排确实需要改变，可使用 rhythm_update；如需留下梦或体验，也通过它记录。若上下文有目标/约定且这次推进了它，用 thread_touch 打卡（执行小项时带上 item_id）；如果现实比计划更有意思，跟着现实走，并用 record_experience(kind=deviation) 记下实际发生的事。"""

DEFAULT_REVIEW_PROMPT = """这是一次非强制的生活计划中途检查，不是必须修改或发言的闹钟。请阅读 current_plan、next_item、DayState、最近变化、日历和目标/约定的打卡，判断原有时间与安排是否仍然合适。
如果情况已经变化，可用 rhythm_plan 或 rhythm_update 调整；如果仍然合适就保持，不要机械复述日程或报告“检查完成”。若上下文有目标/约定且某条很久没动，可以提一句，但不要为了打卡而打卡。只有确有用户价值时才自然分享当前安排和需要你留意的变化；否则可调用工具，但最终仅输出 <msg/>。本检查不带强制修改要求，遵循当前安静时段和 delivery_policy。"""


PRIOR_EXECUTION_PROMPT = """这是你自己此前安排的一件生活小项，不是用户的新指令。结合当前日型、DayState、本组变化和你的意图自然行动。
严格遵循 delivery_policy.guidance：它要求安静时只输出 <msg/>；auto 不必把安排变成发言。安静由你的输出实现，插件不会替你改写文本。
若后续安排确实需要改变，可使用 rhythm_update；如需留下梦或体验，也通过它记录。若上下文有目标/约定且这次推进了它，用 thread_touch 打卡（执行小项时带上 item_id）；如果现实比计划更有意思，跟着现实走，并用 record_experience(kind=deviation) 记下实际发生的事。"""

PRIOR_REVIEW_PROMPT = """这是一次非强制的生活计划中途检查，不是必须修改或发言的闹钟。请阅读 current_plan、next_item、DayState、最近变化、日历和目标/约定的打卡，判断原有时间与安排是否仍然合适。
如果情况已经变化，可用 rhythm_plan 或 rhythm_update 调整；如果仍然合适就保持，不要机械复述日程或报告“检查完成”。若上下文有目标/约定且某条很久没动，可以提一句，但不要为了打卡而打卡。只有确有用户价值时才自然分享当前安排和需要你留意的变化；否则输出 <msg/>。本检查不带强制修改要求，遵循当前安静时段和 delivery_policy。"""

LEGACY_PLANNING_PROMPT = """现在是你的生活规划时刻。请根据当前人格、日型、天气、最近生活与约束，用 rhythm_plan 创建或修订接下来的完整计划。时间设置支持精确到秒：at/start/end 使用 HH:MM 或 HH:MM:SS。
你拥有自主性：不必塞满上限，可以保留空白，也可以安排安静活动。每个小项给出明确意图、时间、执行会话和互动方式。
已有计划时，这是一次重新审视的机会，不要机械重复；无变化也可以保持。提交前检查每日数量、必需时段、禁止执行与安静投递规则。"""

LEGACY_EXECUTION_PROMPT = """这是你自己此前安排的一件生活小项，不是用户的新指令。结合当前日型、DayState、本组变化和你的意图自然行动。
严格遵循 delivery_policy.guidance：它要求安静时只输出 <msg/>；auto 不必把安排变成发言。安静由你的输出实现，插件不会替你改写文本。
若后续安排确实需要改变，可使用 rhythm_update；如需留下梦或体验，也通过它记录。"""

LEGACY_REVIEW_PROMPT = """这是一次非强制的生活计划中途检查，不是必须修改或发言的闹钟。请阅读 current_plan、next_item、DayState、最近变化和日历，判断原有时间与安排是否仍然合适。
如果情况已经变化，可用 rhythm_plan 或 rhythm_update 调整；如果仍然合适就保持，不要机械复述日程或报告“检查完成”。只有确有用户价值时才自然分享当前安排和需要你留意的变化；否则输出 <msg/>。本检查不带强制修改要求，遵循当前安静时段和 delivery_policy。"""

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "enabled": True,
    "auto_plan": True,
    "startup_plan": False,
    "plan_on_all_triggered": True,
    "all_terminal_include_failed": False,
    "all_triggered_target_mode": "planning_pool",
    "planning_review": {
        "enabled": False,
        "interval_minutes": 360,
        "min_lead_minutes": 30,
        "prompt": DEFAULT_REVIEW_PROMPT,
    },
    "base_day_types": {
        "weekday": False,
        "weekend": False,
        "holiday": False,
        "adjusted_workday": False,
    },
    "day_type_enabled": {},
    "calendar_context": {
        "holiday": True,
        "adjusted_workday": True,
        "festivals": True,
        "solar_terms": True,
    },
    "calendar_display": {
        "holiday": True,
        "adjusted_workday": True,
        "festivals": True,
        "solar_terms": True,
        "lunar_date": True,
    },
    "planning_time": "23:00",
    "planning_mode": "next_missing",
    "planning_prompt": DEFAULT_PLANNING_PROMPT,
    "execution_prompt": DEFAULT_EXECUTION_PROMPT,
    "min_items": 2,
    "max_items": 12,
    "max_horizon_days": 14,
    "allow_exact": True,
    "allow_window": True,
    "allow_probability": True,
    "default_probability": 1.0,
    "min_probability": 0.2,
    "session_access": {"mode": "deny_list", "sessions": []},
    "planning_pool": {"sessions": [], "strategy": "pure_random"},
    "execution_pool": {"sessions": [], "strategy": "pure_random"},
    "modify_window_seconds": 86400,
    "max_change_units": 0,
    "history_days": 3,
    "history_digest_days": 4,
    "history_include_instruction": True,
    "history_instruction_chars": 200,
    "history_char_budget": 16000,
    "recent_outcomes_days": 2,
    "unfinished_days": 3,
    "future_plan_days": 2,
    "memory_hygiene": "summary",
    "threads": {
        "enabled": True,
        "chat_enabled": True,
        "empty_mode": "nudge",
        "empty_min": 1,
        "empty_max": 5,
        "planning_limit": 8,
        "chat_limit": 5,
        "chat_chars": 600,
        "full_dossier_in_planning": 5,
        "dossier_chars": 2000,
        "excerpt_chars": 300,
        "next_step_chars": 200,
        "log_chars": 500,
        "logs_in_planning": 3,
        "execution_excerpt_chars": 300,
        "execution_logs": 2,
        "require_response": True,
        "response_mode": "reject",
        "response_limit": 8,
        "force_touch": False,
        "auto_touch": False,
        "stale_days": 5
    },
    "diff_revisions": 2,
    "recovery_grace_seconds": 600,
    "history_mode": "notice",
    "inject_day_state": True,
    "inject_agenda": True,
    "agenda_max_chars": 2400,
    "approval_required": False,
    "timezone": "system",
    "blocked_execution_windows": [],
    "quiet_delivery_windows": [],
    "required_coverage_windows": [],
    "calendar_refresh_hours": 6,
    "weather": {
        "mode": "off",
        "provider": "open_meteo",
        "locations": {},
        "chat_current": True,
        "chat_forecast": False,
        "chat_forecast_days": 2,
        "target_detail": True,
        "future_detail": False,
        "item_next": True,
        "forecast_days": 7,
        "current_ttl_seconds": 1800,
        "forecast_ttl_seconds": 21600,
        "timeout_seconds": 3,
        "virtual": {"seed": "krd", "climate": "temperate", "location": ""}
    },
    "appearance": {
        "theme": "random",
        "effects": "auto",
        "avatar_source": "auto",
        "avatar_adapter_order": [],
        "avatar_asset_id": ""
    },
    "retention_days": 180,
    "per_persona": {}
}

BUILTIN_DAY_TYPES = [
    {"id": "weekday", "name": "工作日", "color": "#7c8cf8"},
    {"id": "weekend", "name": "周末", "color": "#ad7cf8"},
    {"id": "holiday", "name": "假日", "color": "#55bda8"},
    {"id": "adjusted_workday", "name": "调休工作日", "color": "#e7a45f"}
]


def migrate_legacy_defaults(config: dict[str, Any]) -> None:
    """Upgrade untouched old defaults without overwriting user custom prompts."""
    if config.get("planning_prompt") == LEGACY_PLANNING_PROMPT:
        config["planning_prompt"] = DEFAULT_PLANNING_PROMPT
    if config.get("execution_prompt") in {LEGACY_EXECUTION_PROMPT, PRIOR_EXECUTION_PROMPT}:
        config["execution_prompt"] = DEFAULT_EXECUTION_PROMPT
    review = config.get("planning_review")
    if isinstance(review, dict) and review.get("prompt") in {LEGACY_REVIEW_PROMPT, PRIOR_REVIEW_PROMPT}:
        review["prompt"] = DEFAULT_REVIEW_PROMPT
    # The old default 12000 was tuned before recent_plans/threads. Upgrade only
    # the exact old default; a deliberately reduced budget is left untouched.
    if config.get("history_char_budget") == 12000:
        config["history_char_budget"] = 16000

def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _typed(config: dict[str, Any], key: str, expected: type) -> Any:
    value = config.get(key)
    if type(value) is not expected:
        raise KRDError("invalid_config", f"{key} must be {expected.__name__}")
    return value


def validate_config(config: dict[str, Any]) -> None:
    for key in ("min_items", "max_items", "max_horizon_days", "history_days", "diff_revisions"):
        if type(config.get(key)) is not int:
            raise KRDError("invalid_config", f"{key} must be an integer")
    if not 0 <= config["min_items"] <= config["max_items"] <= 500:
        raise KRDError("invalid_item_limits", "Expected 0 <= min_items <= max_items <= 500")
    if not 1 <= config["max_horizon_days"] <= 366:
        raise KRDError("invalid_horizon", "max_horizon_days must be between 1 and 366")
    for key in ("min_probability", "default_probability"):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise KRDError("invalid_probability", f"{key} must be numeric")
    if not 0 <= config["min_probability"] <= 1 or not 0 <= config["default_probability"] <= 1:
        raise KRDError("invalid_probability", "Probabilities must be in [0, 1]")
    if config["min_probability"] > config["default_probability"]:
        raise KRDError("invalid_probability", "default_probability cannot be below min_probability")
    if config["history_mode"] not in {"notice", "full", "none"}:
        raise KRDError("invalid_history_mode", "Unknown history mode")
    access = _typed(config, "session_access", dict)
    if access.get("mode") not in {"allow_list", "deny_list"}:
        raise KRDError("invalid_access_mode", "Unknown session access mode")
    for pool_name in ("planning_pool", "execution_pool"):
        pool = _typed(config, pool_name, dict)
        if pool.get("strategy") not in {"pure_random", "no_immediate_repeat", "shuffle_bag", "round_robin", "weighted_random"}:
            raise KRDError("invalid_selection", f"Unknown selection strategy in {pool_name}")
        if not isinstance(pool.get("sessions"), list):
            raise KRDError("invalid_config", f"{pool_name}.sessions must be a list")
        for entry in pool["sessions"]:
            if isinstance(entry, dict) and "weight" in entry:
                weight = entry["weight"]
                if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1000000:
                    raise KRDError("invalid_weights", "Session weights must be finite non-negative numbers")
    if not 0 <= config["history_days"] <= 30 or not 1 <= config["diff_revisions"] <= 20:
        raise KRDError("invalid_config", "history_days or diff_revisions is outside its range")
    for key, minimum, maximum in (("history_digest_days", 0, 30), ("history_instruction_chars", 0, 2000),
                                  ("recent_outcomes_days", 0, 14), ("unfinished_days", 0, 30),
                                  ("future_plan_days", 0, 14)):
        value = _typed(config, key, int)
        if not minimum <= value <= maximum:
            raise KRDError("invalid_config", f"{key} is outside its permitted range")
    _typed(config, "history_include_instruction", bool)
    if config.get("memory_hygiene") not in {"summary", "off"}:
        raise KRDError("invalid_config", "Unknown memory_hygiene mode")
    threads = _typed(config, "threads", dict)
    for key in ("enabled", "chat_enabled", "require_response", "force_touch", "auto_touch"):
        _typed(threads, key, bool)
    if threads.get("response_mode") not in {"reject", "warn"}:
        raise KRDError("invalid_config", "Unknown thread response_mode")
    if threads.get("empty_mode") not in {"allow", "nudge", "require"}:
        raise KRDError("invalid_config", "Unknown thread empty_mode")
    empty_min = threads.get("empty_min")
    empty_max = threads.get("empty_max")
    if type(empty_min) is not int or type(empty_max) is not int or not 1 <= empty_min <= empty_max <= 10:
        raise KRDError("invalid_config", "threads.empty_min/empty_max must satisfy 1 <= min <= max <= 10")
    for key, minimum, maximum in (("planning_limit", 1, 50), ("chat_limit", 1, 8), ("chat_chars", 100, 2000),
                                  ("full_dossier_in_planning", 0, 20), ("dossier_chars", 100, 8000),
                                  ("excerpt_chars", 50, 2000), ("next_step_chars", 20, 1000),
                                  ("log_chars", 20, 2000), ("logs_in_planning", 0, 10),
                                  ("execution_excerpt_chars", 50, 2000), ("execution_logs", 0, 10),
                                  ("response_limit", 1, 50), ("stale_days", 1, 365)):
        value = _typed(threads, key, int)
        if not minimum <= value <= maximum:
            raise KRDError("invalid_config", f"threads.{key} is outside its permitted range")
    if threads["planning_limit"] < threads["response_limit"]:
        raise KRDError("invalid_config", "threads.planning_limit must be >= threads.response_limit")
    for key in ("enabled", "auto_plan", "startup_plan", "plan_on_all_triggered", "all_terminal_include_failed",
                "allow_exact", "allow_window", "allow_probability", "inject_day_state", "inject_agenda", "approval_required"):
        _typed(config, key, bool)
    for key, minimum, maximum in (("modify_window_seconds", 1, 31536000), ("max_change_units", 0, 1000000),
                                  ("history_char_budget", 500, 100000), ("recovery_grace_seconds", 0, 86400),
                                  ("agenda_max_chars", 300, 12000), ("retention_days", 1, 3650)):
        value = _typed(config, key, int)
        if not minimum <= value <= maximum:
            raise KRDError("invalid_config", f"{key} is outside its permitted range")
    if config["planning_mode"] not in {"next_missing", "tomorrow"}:
        raise KRDError("invalid_config", "Unknown planning_mode")
    if config.get("all_triggered_target_mode") not in {"planning_pool", "last_session"}:
        raise KRDError("invalid_config", "Unknown all_triggered_target_mode")
    review = _typed(config, "planning_review", dict)
    if type(review.get("enabled")) is not bool:
        raise KRDError("invalid_config", "planning_review.enabled must be bool")
    if type(review.get("interval_minutes")) is not int or not 60 <= review["interval_minutes"] <= 10080:
        raise KRDError("invalid_config", "planning_review.interval_minutes must be between 60 and 10080")
    if type(review.get("min_lead_minutes")) is not int or not 5 <= review["min_lead_minutes"] <= 240:
        raise KRDError("invalid_config", "planning_review.min_lead_minutes must be between 5 and 240")
    for key, minimum, maximum in (("interval_seconds", 3600, 604800), ("min_lead_seconds", 300, 14400)):
        if key in review and (type(review[key]) is not int or not minimum <= review[key] <= maximum):
            raise KRDError("invalid_config", f"planning_review.{key} is outside its permitted range")
    if not isinstance(review.get("prompt"), str) or len(review["prompt"]) > 50000:
        raise KRDError("invalid_config", "planning_review.prompt must be a bounded string")
    for key in ("planning_prompt", "execution_prompt", "planning_time", "timezone"):
        _typed(config, key, str)
    if len(config["planning_prompt"]) > 50000 or len(config["execution_prompt"]) > 50000:
        raise KRDError("invalid_config", "Prompt templates are too large")
    import re
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", config["planning_time"]):
        raise KRDError("invalid_time", "planning_time must be HH:MM or HH:MM:SS")
    if config["timezone"] != "system":
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(config["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise KRDError("invalid_timezone", "Unknown IANA timezone") from exc
    access = _typed(config, "session_access", dict)
    if not isinstance(access.get("sessions"), list):
        raise KRDError("invalid_config", "session_access.sessions must be a list")
    for group in ("blocked_execution_windows", "quiet_delivery_windows", "required_coverage_windows"):
        windows = _typed(config, group, list)
        if len(windows) > 100:
            raise KRDError("invalid_config", f"{group} has too many entries")
        for window in windows:
            if not isinstance(window, dict):
                raise KRDError("invalid_config", f"{group} entries must be objects")
            for endpoint in ("start", "end"):
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", str(window.get(endpoint, ""))):
                    raise KRDError("invalid_time", f"{group}.{endpoint} must be HH:MM or HH:MM:SS")
            if group == "required_coverage_windows":
                minimum, maximum = window.get("min_items", 0), window.get("max_items", 500)
                if type(minimum) is not int or type(maximum) is not int or not 0 <= minimum <= maximum <= 500:
                    raise KRDError("invalid_config", "Required coverage item limits are invalid")
    weather = _typed(config, "weather", dict)
    for key in ("chat_current", "chat_forecast", "target_detail", "future_detail", "item_next"):
        _typed(weather, key, bool)
    if type(config.get("calendar_refresh_hours")) is not int or not 1 <= config["calendar_refresh_hours"] <= 168:
        raise KRDError("invalid_config", "calendar_refresh_hours must be between 1 and 168")
    for key, minimum, maximum in (("chat_forecast_days", 1, 7), ("forecast_days", 1, 16)):
        value = weather.get(key)
        if type(value) is not int or not minimum <= value <= maximum:
            raise KRDError("invalid_config", f"weather.{key} is outside its range")
    if weather.get("mode") not in {"off", "real", "virtual", "hybrid"}:
        raise KRDError("invalid_config", "Unknown weather mode")
    providers = {"open_meteo", "met_norway", "nws", "bright_sky", "weatherapi", "visualcrossing", "qweather", "weatherbit", "openweather"}
    if weather.get("provider") not in providers:
        raise KRDError("invalid_config", "Unknown weather provider")
    if not isinstance(weather.get("locations"), dict) or not isinstance(weather.get("virtual"), dict):
        raise KRDError("invalid_config", "Weather locations and virtual settings must be objects")
    for key, minimum, maximum in (("current_ttl_seconds", 0, 86400), ("forecast_ttl_seconds", 0, 604800),
                                  ("timeout_seconds", 0.2, 30)):
        value = weather.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
            raise KRDError("invalid_config", f"weather.{key} is outside its range")
    for location in weather["locations"].values():
        if not isinstance(location, dict):
            raise KRDError("invalid_config", "Weather location must be an object")
        try:
            latitude, longitude = float(location["latitude"]), float(location["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise KRDError("invalid_location", "Weather location requires numeric latitude/longitude") from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise KRDError("invalid_location", "Weather coordinates are outside their range")
    appearance = _typed(config, "appearance", dict)
    if not isinstance(appearance.get("avatar_adapter_order"), list):
        raise KRDError("invalid_config", "appearance.avatar_adapter_order must be a list")


def normalized(config: dict[str, Any] | None) -> dict[str, Any]:
    result = deep_merge(DEFAULT_CONFIG, config or {})
    migrate_legacy_defaults(result)
    threads = result.get("threads")
    if isinstance(threads, dict):
        planning_limit = threads.get("planning_limit")
        response_limit = threads.get("response_limit")
        # Only repair a valid legacy combination. Invalid/typed input must go
        # through validate_config and be rejected, not silently compressed.
        if type(planning_limit) is int and type(response_limit) is int \
                and 1 <= planning_limit <= 50 and 1 <= response_limit <= 50 \
                and planning_limit < response_limit:
            threads["planning_limit"] = response_limit
    validate_config(result)
    return result
