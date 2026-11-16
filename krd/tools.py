from __future__ import annotations

from datetime import datetime, timedelta

from .models import KRDError, compact_error
from .store import dumps
from .llm_format import prepare_llm_payload


def runtime_from_event(event):
    runtime = getattr(event, "_krd_runtime", None)
    if runtime is None:
        raise KRDError("runtime_unavailable", "KRD runtime is unavailable")
    return runtime


def error_result(exc: Exception) -> str:
    return dumps(compact_error(exc))

def host_tz(runtime):
    try:
        return getattr(runtime.ctx.get_timezone(), 'key', None)
    except Exception:
        return None


async def rhythm_plan(event, plan: dict | None = None, plans: list[dict] | None = None,
                      mode: str = "revise", reason: str = "", **kwargs) -> str:
    try:
        runtime = runtime_from_event(event)
        persona_id = await runtime.active_persona_id()
        payloads = plans or ([plan] if plan else [])
        results = await runtime.plans.apply_many(persona_id, payloads, actor="bot", mode=mode, reason=reason)
        for metadata in runtime.context_builder.metadata(event):
            if metadata["kind"] in {"planning", "review"}:
                await runtime.store.execute("UPDATE planning_runs SET status='completed',finished_at=? WHERE id=?", (__import__('time').time(), metadata["run_id"]))
        await runtime.broadcast("plan_changed", {"persona_id": persona_id, "days": [r["plan"]["date"] for r in results]})
        payload = {"ok": True, "days": [{"plan_id": r["plan"]["id"], "date": r["plan"]["date"], "revision": r["revision"],
                                          "diff": r["diff"], "change_units": r["change_units"]} for r in results]}
        cfg = await runtime.store.get_config(persona_id)
        tz_name = runtime.plans.policy.timezone_name(cfg)
        host = host_tz(runtime)
        if host != tz_name:
            payload["timezone"] = tz_name
        return dumps(prepare_llm_payload(payload, tz_name, host, drop=("source",)))
    except Exception as exc:
        return error_result(exc)


async def rhythm_update(event, operations: list[dict], reason: str = "", **kwargs) -> str:
    try:
        runtime = runtime_from_event(event)
        persona_id = await runtime.active_persona_id()
        if not isinstance(operations, list) or not operations or len(operations) > 50:
            raise KRDError("invalid_operations", "Provide 1–50 operations")
        results = []
        changed_plan_ids = set()
        async with runtime.store.transaction():
            for operation in operations:
                if not isinstance(operation, dict):
                    raise KRDError("invalid_operation", "Each operation must be an object")
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
                    changed_plan_ids.add(result["plan"]["id"])
                elif kind == "append_item":
                    result = await runtime.plans.append_item(
                        persona_id, operation["plan_id"], operation.get("block_title", "生活片段"),
                        operation.get("item") or {}, actor="bot", reason=reason)
                else:
                    raise KRDError("invalid_operation", f"Unknown operation type: {kind}")
                results.append({"type": kind, "result": result})
        for plan_id in changed_plan_ids:
            await runtime.scheduler.check_all_triggered(plan_id)
        runtime.scheduler.wake()
        await runtime.broadcast("data_changed", {"persona_id": persona_id, "source": "rhythm_update"})
        cfg = await runtime.store.get_config(persona_id)
        tz_name = runtime.plans.policy.timezone_name(cfg)
        host = host_tz(runtime)
        payload = {"ok": True, "results": results}
        if host != tz_name:
            payload["timezone"] = tz_name
        return dumps(prepare_llm_payload(payload, tz_name, host, drop=("source",)))
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
        if scope == "calendar":
            end = end or date or today
            start = start or end
            result = await runtime.calendar.range(start, end, allow_network=False)
        elif scope in {"current", "today"}:
            result = {"date": today, "day_state": await plans_service.day_state(persona_id, today),
                      "plan": await plans_service.get_plan_by_date(persona_id, today)}
        elif scope == "block":
            if not item_id:
                raise KRDError("item_required", "item_id is required for block view")
            item_id = await runtime.plans.resolve_item_id(persona_id, item_id)
            row = await runtime.store.one("SELECT plan_id,block_id FROM items WHERE id=?", (item_id,))
            if not row:
                raise KRDError("not_found", "Item not found")
            plan = await plans_service.get_plan(row["plan_id"], persona_id)
            if plan is None:
                raise KRDError("not_found", "Item not found in the active persona")
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
            result = await plans_service.revisions(plan_id, limit, persona_id)
        elif scope == "quota":
            config = await runtime.store.get_config(persona_id)
            row = await runtime.store.one(
                "SELECT COALESCE(SUM(m.units),0) AS used FROM mutations m JOIN plans p ON p.id=m.plan_id "
                "WHERE m.actor='bot' AND p.persona_id=? AND m.created_at>=?",
                (persona_id, __import__('time').time() - config["modify_window_seconds"]))
            result = {"used": row["used"], "limit": config["max_change_units"], "window_seconds": config["modify_window_seconds"]}
        elif scope == "experiences":
            result = await plans_service.experiences(persona_id, date or None, item_id, limit)
        else:
            raise KRDError("invalid_scope", f"Unknown view scope: {scope}")
        cfg = await runtime.store.get_config(persona_id)
        tz_name = runtime.plans.policy.timezone_name(cfg)
        host = host_tz(runtime)
        payload = {"ok": True, "scope": scope, "result": result}
        if host != tz_name:
            payload["timezone"] = tz_name
        return dumps(prepare_llm_payload(payload, tz_name, host, drop=("source",)))
    except Exception as exc:
        return error_result(exc)
