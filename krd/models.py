from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

TERMINAL_ITEM_STATES = {"triggered", "triggered_silent", "skipped_probability", "missed", "cancelled"}
ACTIVE_ITEM_STATES = {"scheduled", "queued", "running"}
RUNNING_RUN_STATES = {"prepared", "queued", "running"}
INTERACTIONS = {"auto", "must_message", "silent"}
HISTORY_MODES = {"notice", "full", "none"}
SELECTION_STRATEGIES = {"pure_random", "no_immediate_repeat", "shuffle_bag", "round_robin", "weighted_random"}


class KRDError(ValueError):
    """Typed error safe to return to an LLM, API client, or log."""

    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass(frozen=True)
class Result:
    value: Any = None
    meta: dict[str, Any] = field(default_factory=dict)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def now() -> float:
    return time.time()


def compact_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, KRDError):
        return {"error": exc.as_dict()}
    return {"error": {"code": "internal_error", "message": str(exc), "details": {}}}
