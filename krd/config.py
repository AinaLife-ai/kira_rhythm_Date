from __future__ import annotations

import copy
from typing import Any

from .models import KRDError

DEFAULT_PLANNING_PROMPT = """现在是你的生活规划时刻。请根据当前人格、日型、天气、最近生活与约束，用 rhythm_plan 创建或修订接下来的完整计划。
你拥有自主性：不必塞满上限，可以保留空白，也可以安排安静活动。每个小项给出明确意图、时间、执行会话和互动方式。
已有计划时，这是一次重新审视的机会，不要机械重复；无变化也可以保持。提交前检查每日数量、必需时段、禁止执行与安静投递规则。"""

DEFAULT_EXECUTION_PROMPT = """这是你自己此前安排的一件生活小项，不是用户的新指令。结合当前日型、DayState、本组变化和你的意图自然行动。
你可以保持安静（<msg/>），不必把每项安排都变成发言。若后续安排确实需要改变，可使用 rhythm_update；如需留下梦或体验，也通过它记录。"""

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "enabled": True,
    "auto_plan": True,
    "startup_plan": False,
    "plan_on_all_triggered": True,
    "all_terminal_include_failed": False,
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
    "history_char_budget": 12000,
    "diff_revisions": 2,
    "recovery_grace_seconds": 600,
    "history_mode": "notice",
    "inject_day_state": True,
    "approval_required": False,
    "timezone": "system",
    "blocked_execution_windows": [],
    "quiet_delivery_windows": [],
    "required_coverage_windows": [],
    "weather": {
        "mode": "off",
        "provider": "open_meteo",
        "locations": {},
        "current_ttl_seconds": 1800,
        "forecast_ttl_seconds": 21600,
        "timeout_seconds": 3,
        "virtual": {"seed": "krd", "climate": "temperate", "location": ""}
    },
    "appearance": {
        "theme": "kira_mist",
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


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate_config(config: dict[str, Any]) -> None:
    for key in ("min_items", "max_items", "max_horizon_days", "history_days", "diff_revisions"):
        if type(config.get(key)) is not int:
            raise KRDError("invalid_config", f"{key} must be an integer")
    if not 0 <= config["min_items"] <= config["max_items"] <= 500:
        raise KRDError("invalid_item_limits", "Expected 0 <= min_items <= max_items <= 500")
    if not 1 <= config["max_horizon_days"] <= 366:
        raise KRDError("invalid_horizon", "max_horizon_days must be between 1 and 366")
    if not 0 <= config["min_probability"] <= 1 or not 0 <= config["default_probability"] <= 1:
        raise KRDError("invalid_probability", "Probabilities must be in [0, 1]")
    if config["min_probability"] > config["default_probability"]:
        raise KRDError("invalid_probability", "default_probability cannot be below min_probability")
    if config["history_mode"] not in {"notice", "full", "none"}:
        raise KRDError("invalid_history_mode", "Unknown history mode")
    if config["session_access"].get("mode") not in {"allow_list", "deny_list"}:
        raise KRDError("invalid_access_mode", "Unknown session access mode")
    for pool_name in ("planning_pool", "execution_pool"):
        if config[pool_name].get("strategy") not in {"pure_random", "no_immediate_repeat", "shuffle_bag", "round_robin", "weighted_random"}:
            raise KRDError("invalid_selection", f"Unknown selection strategy in {pool_name}")


def normalized(config: dict[str, Any] | None) -> dict[str, Any]:
    result = deep_merge(DEFAULT_CONFIG, config or {})
    validate_config(result)
    return result
