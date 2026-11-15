from __future__ import annotations

from datetime import datetime
from typing import Any

from .timeutils import timezone

# Fields that are machine timestamps in storage but should be readable to an LLM.
_TIME_KEYS = {
    "scheduled_at", "created_at", "updated_at", "claimed_at", "finished_at",
    "started_at", "expires_at", "timestamp", "run_at",
}


def readable_time(timestamp: Any, tz_name: str) -> str:
    """Return a local, human-readable timestamp for LLM-facing payloads."""
    try:
        value = float(timestamp)
    except (TypeError, ValueError):
        return str(timestamp)
    return datetime.fromtimestamp(value, timezone(tz_name)).strftime("%Y-%m-%d %H:%M:%S")


def humanize_timestamps(value: Any, tz_name: str) -> Any:
    """Recursively replace epoch timestamp fields with local readable text.

    The database and HTTP API keep raw epoch values. Only context/tool results
    sent to the model are transformed; seconds are preserved so the model can
    revise a schedule without silently dropping precision.
    """
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in _TIME_KEYS and isinstance(item, (int, float)) and item > 100_000_000:
                result[key] = readable_time(item, tz_name)
            else:
                result[key] = humanize_timestamps(item, tz_name)
        return result
    if isinstance(value, list):
        return [humanize_timestamps(item, tz_name) for item in value]
    return value


def prepare_llm_payload(value: Any, tz_name: str, host_tz_name: str | None = None,
                        drop: tuple[str, ...] = ()) -> Any:
    """Compact and humanize a payload before sending it to the model.

    - removes persona_id and explicitly requested internal fields
    - removes null fields (nothing useful for the model to read)
    - removes timezone when it already equals the KiraAI host setting
    """
    cleaned = humanize_timestamps(value, tz_name)
    drop_keys = {"persona_id", *drop}

    def walk(item: Any) -> Any:
        if isinstance(item, dict):
            result = {}
            for key, val in item.items():
                if key in drop_keys or val is None:
                    continue
                if key == "timezone" and host_tz_name and val == host_tz_name:
                    continue
                result[key] = walk(val)
            return result
        if isinstance(item, list):
            return [walk(entry) for entry in item]
        return item

    return walk(cleaned)
