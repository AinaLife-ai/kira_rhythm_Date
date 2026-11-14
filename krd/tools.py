from __future__ import annotations

from datetime import datetime, timedelta

from .models import KRDError, compact_error
from .store import dumps


def runtime_from_event(event):
    runtime = getattr(event, "_krd_runtime", None)
    if runtime is None:
        raise KRDError("runtime_unavailable", "KRD runtime is unavailable")
    return runtime


def error_result(exc: Exception) -> str:
    return dumps(compact_error(exc))


async def rhythm_plan(event, plan: dict | None = None, plans: list[dict] | None = None,
                      mode: str = "revise", reason: str = "", **kwargs) -> str:
    try:
        runtime = runtime_from_event(event)
        persona_id = await runtime.active_persona_id()
        payloads = plans or ([plan] if plan else [])
        results = await runtime.plans.apply_many(persona_id, payloads, actor="bot", mode=mode, reason=reason)
        for metadata in runtime.context_builder.metadata(event):
            if metadata["kind"] == "planning":
                await runtime.store.execute("UPDATE planning_runs SET status='completed',finished_at=? WHERE id=?", (__import__('time').time(), metadata["run_id"]))
        return dumps({"ok": True, "days": [{"plan_id": r["plan"]["id"], "date": r["plan"]["date"], "revision": r["revision"],
                                           "diff": r["diff"], "change_units": r["change_units"]} for r in results]})
    except Exception as exc:
        return error_result(exc)


async def rhythm_update(event, operations: list[dict], reason: str = "", **kwargs) -> str:
    try:
        runtime = runtime_from_event(event)
        persona_id = await runtime.active_persona_id()
        if not isinstance(operations, list) or not operations or len(operations) > 50:
            raise KRDError("invalid_operations", "Provide 1–50 operations")
        results = []
        for operation in operations:
            kind = operation.get("type")
            if kind == "day_state":
                day = operation.get("date") or await runtime.plans.current_date(persona_id)
                patch = operation.get("patch") or {key: value for key, value in operation.items()
                                                   if key.startswith("current_")}
                result = await runtime.plans.set_day_state(persona_id, day, patch, "bot", reason)
            elif kind == "record_experience":
                day = operation.get("date") or await runtime.plans.current_date(persona_id)
                result = await runtime.plans.record_experience(
                    persona_id, day, str(operation.get("content", "")), kind=operation.get("kind", "note"),
                    item_id=operation.get("item_id", ""))
            elif kind == "update_item":
                patch = operation.get("patch") or {key: value for key, value in operation.items() if key not in {"type", "item_id"}}
                result = await runtime.plans.update_item(persona_id, operation["item_id"], patch, actor="bot", reason=reason)
            elif kind == "append_item":
                result = await runtime.plans.append_item(
                    persona_id, operation["plan_id"], operation.get("block_title", "生活片段"),
                    operation.get("item") or {}, actor="bot", reason=reason)
            else:
                raise KRDError("invalid_operation", f"Unknown operation type: {kind}")
            results.append({"type": kind, "result": result})
        await runtime.scheduler.wake()
        return dumps({"ok": True, "results": results})
    except Exception as exc:
        return error_result(exc)


async def rhythm_view(event, scope: str = "current", date: str = "", start: str = "", end: str = "",
                      plan_id: str = "", item_id: str = "", limit: int = 20, **kwargs) -> str:
    try:
        runtime = runtime_from_event(event)
        persona_id = await runtime.active_persona_id()
        plans_service = runtime.plans
        today = date or await plans_service.current_date(persona_id)
        limit = max(1, min(100, int(limit)))
        if scope in {"current", "today"}:
            result = {"date": today, "day_state": await plans_service.day_state(persona_id, today),
                      "plan": await plans_service.get_plan_by_date(persona_id, today)}
        elif scope == "block":
            if not item_id:
                raise KRDError("item_required", "item_id is required for block view")
            row = await runtime.store.one("SELECT plan_id,block_id FROM items WHERE id=?", (item_id,))
            if not row:
                raise KRDError("not_found", "Item not found")
            plan = await plans_service.get_plan(row["plan_id"], persona_id)
            result = next((block for block in plan["blocks"] if block["id"] == row["block_id"]), None)
        elif scope == "day":
            result = await plans_service.get_plan_by_date(persona_id, today)
        elif scope in {"range", "history"}:
            config = await runtime.store.get_config(persona_id)
            end = end or (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
            start = start or (datetime.fromisoformat(end) - timedelta(days=config["history_days"] - 1)).date().isoformat()
            result = await plans_service.list_plans(persona_id, start, end)
        elif scope == "diff":
            if not plan_id:
                raise KRDError("plan_required", "plan_id is required for diff view")
            result = await plans_service.revisions(plan_id, limit)
        elif scope == "quota":
            config = await runtime.store.get_config(persona_id)
            row = await runtime.store.one(
                "SELECT COALESCE(SUM(units),0) AS used FROM mutations WHERE actor='bot' AND created_at>=?",
                (__import__('time').time() - config["modify_window_seconds"],))
            result = {"used": row["used"], "limit": config["max_change_units"], "window_seconds": config["modify_window_seconds"]}
        elif scope == "experiences":
            result = await plans_service.experiences(persona_id, date or None, item_id, limit)
        else:
            raise KRDError("invalid_scope", f"Unknown view scope: {scope}")
        return dumps({"ok": True, "scope": scope, "result": result})
    except Exception as exc:
        return error_result(exc)
