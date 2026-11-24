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
        cfg = await runtime.store.get_config(persona_id)
        metadata = runtime.context_builder.metadata(event)
        planning_meta = next((item for item in metadata if item.get("kind") == "planning"), None)
        warnings = []
        if planning_meta and runtime.threads is not None:
            settings = cfg.get("threads", {})
            if settings.get("enabled", True) and settings.get("empty_mode") == "require":
                try:
                    active_threads = await runtime.threads.active_count(persona_id)
                except Exception:
                    active_threads = 1
                empty_min = int(settings.get("empty_min", 1))
                if active_threads < empty_min:
                    raise KRDError(
                        "thread_seed_required",
                        f"目标层活动目标不足；本次规划要求至少 {empty_min} 条",
                        hint="先用 rhythm_update 的 thread_add 建立真实目标，再提交 rhythm_plan。")
        if planning_meta and runtime.threads is not None:
            try:
                missing = await runtime.threads.missing_for_run(planning_meta["run_id"])
            except Exception:
                missing = []
            if missing:
                settings = cfg.get("threads", {})
                # The run persisted its required ids. A later config toggle must
                # not silently waive a contract that the prompt still shows.
                if settings.get("response_mode", "reject") == "reject":
                    raise KRDError(
                        "thread_response_required",
                        "本次规划还没有回应目标/约定",
                        missing=missing,
                        hint="先调用 rhythm_update 的 thread_response；no_change 也合法。")
                warnings.append({"code": "thread_response_missing", "missing": missing})
        payloads = plans or ([plan] if plan else [])
        results = await runtime.plans.apply_many(persona_id, payloads, actor="bot", mode=mode, reason=reason)
        if planning_meta and runtime.threads is not None:
            try:
                advances = await runtime.store.all(
                    "SELECT thread_id FROM thread_responses WHERE run_id=? AND response='advance'",
                    (planning_meta["run_id"],))
                linked = {item.get("thread_id") for result in results
                          for block in result["plan"].get("blocks", [])
                          for item in block.get("items", [])}
                for row in advances:
                    if row["thread_id"] not in linked:
                        warnings.append({"code": "advance_without_item",
                                         "thread_id": row["thread_id"],
                                         "hint": "回应为 advance，但计划里没有关联该 thread_id 的小项。"})
            except Exception:
                pass
        for meta in metadata:
            if meta["kind"] in {"planning", "review"}:
                await runtime.store.execute(
                    "UPDATE planning_runs SET status='completed',finished_at=? WHERE id=?",
                    (__import__('time').time(), meta["run_id"]))
                if runtime.threads is not None:
                    try:
                        await runtime.threads.finalize_run(meta["run_id"])
                    except Exception:
                        pass
        await runtime.broadcast("plan_changed", {"persona_id": persona_id, "days": [r["plan"]["date"] for r in results]})
        payload = {"ok": True, "days": [{"plan_id": r["plan"]["id"], "date": r["plan"]["date"], "revision": r["revision"],
                                          "diff": r["diff"], "change_units": r["change_units"]} for r in results]}
        if warnings:
            payload["warnings"] = warnings
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
        metadata = runtime.context_builder.metadata(event)
        planning_meta = next((item for item in metadata if item.get("kind") == "planning"), None)
        run_id = planning_meta["run_id"] if planning_meta else ""
        cfg = await runtime.store.get_config(persona_id)
        threads_enabled = bool(cfg.get("threads", {}).get("enabled", True))
        results = []
        thread_responses = []
        changed_plan_ids = set()
        deleted_plan_ids = set()
        async with runtime.store.transaction():
            for operation in operations:
                if not isinstance(operation, dict):
                    raise KRDError("invalid_operation", "Each operation must be an object")
                kind = operation.get("type")
                if kind in {"thread_add", "thread_touch", "thread_update", "thread_close",
                            "thread_response", "thread_delete"} and runtime.threads is None:
                    raise KRDError("runtime_unavailable", "Thread service is unavailable")
                if kind in {"thread_add", "thread_touch", "thread_update", "thread_close",
                            "thread_delete"} and not threads_enabled:
                    raise KRDError("threads_disabled", "Threads are disabled for this persona")
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
                    plan_id = str(operation.get("plan_id") or "").strip()
                    if not plan_id:
                        day = str(operation.get("date") or "").strip()
                        if not day:
                            raise KRDError("plan_required", "append_item needs plan_id or date")
                        plan = await runtime.plans.get_plan_by_date(persona_id, day)
                        if plan is None:
                            raise KRDError("plan_not_found", f"No plan on {day}", date=day,
                                           hint="append_item 需要已有计划；先创建或选定日期。")
                        plan_id = plan["id"]
                    block_title = str(operation.get("block_title") or operation.get("block") or "生活片段")
                    raw_item = operation.get("item")
                    if not isinstance(raw_item, dict) or not raw_item:
                        keys = ("title", "intent", "instruction", "schedule", "at", "start", "end",
                                "occurrences", "window_mode", "interval_minutes", "interval_seconds",
                                "target", "interaction", "probability", "execution_probability",
                                "category", "thread_id")
                        raw_item = {key: operation[key] for key in keys if key in operation}
                    result = await runtime.plans.append_item(
                        persona_id, plan_id, block_title, raw_item, actor="bot", reason=reason)
                elif kind == "delete_item":
                    result = await runtime.plans.delete_item(persona_id, operation["item_id"], actor="bot", reason=reason)
                    deleted_plan_ids.add(result["plan"]["id"])
                elif kind == "delete_block":
                    result = await runtime.plans.delete_block(persona_id, operation["block_id"], actor="bot", reason=reason)
                    deleted_plan_ids.add(result["plan"]["id"])
                elif kind == "thread_add":
                    result = await runtime.threads.add(persona_id, operation, actor="bot")
                elif kind == "thread_touch":
                    result = await runtime.threads.touch(
                        persona_id, operation["thread_id"], str(operation.get("note", "")),
                        next_step=operation.get("next_step"), item_id=operation.get("item_id", ""), actor="bot")
                elif kind == "thread_update":
                    patch = operation.get("patch") or {
                        key: value for key, value in operation.items() if key not in {"type", "thread_id", "note"}}
                    result = await runtime.threads.update(
                        persona_id, operation["thread_id"], patch, actor="bot", note=str(operation.get("note", "")))
                elif kind == "thread_close":
                    result = await runtime.threads.close(
                        persona_id, operation["thread_id"], str(operation.get("status", "done")),
                        str(operation.get("note", "")), actor="bot", run_id=run_id)
                elif kind == "thread_response":
                    thread_responses.append(operation)
                    continue
                elif kind == "thread_delete":
                    raise KRDError("permission_denied", "Threads can only be deleted by the user")
                elif kind == "delete_day":
                    raise KRDError("permission_denied", "Whole-day deletion is a user-only action")
                else:
                    raise KRDError("invalid_operation", f"Unknown operation type: {kind}")
                results.append({"type": kind, "result": result})
            if thread_responses:
                if runtime.threads is None:
                    raise KRDError("runtime_unavailable", "Thread service is unavailable")
                if not run_id:
                    raise KRDError("thread_response_outside_planning",
                                   "thread_response is only available during a planning run")
                response_result = await runtime.threads.record_responses(
                    persona_id, run_id, thread_responses, actor="bot")
                results.append({"type": "thread_response", "result": response_result})
        for plan_id in changed_plan_ids - deleted_plan_ids:
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
                      plan_id: str = "", item_id: str = "", thread_id: str = "", status: str = "",
                      kind: str = "", limit: int = 20, **kwargs) -> str:
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
                      "plan": await plans_service.get_plan_by_date(persona_id, today),
                      "recent_changes": await plans_service.recent_changes(persona_id, today, 2, meaningful_only=True)}
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
            plan = await plans_service.get_plan_by_date(persona_id, today)
            result = ({**plan, "recent_changes": await plans_service.recent_changes(persona_id, today, 3, meaningful_only=True)}
                      if plan else {"plan": None, "recent_changes": await plans_service.recent_changes(persona_id, today, 3, meaningful_only=True)})
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
        elif scope == "threads":
            if runtime.threads is None:
                raise KRDError("runtime_unavailable", "Thread service is unavailable")
            result = await runtime.threads.list(
                persona_id, status=status, kind=kind, limit=limit,
                include_deleted=status == "deleted")
        elif scope == "thread":
            if runtime.threads is None:
                raise KRDError("runtime_unavailable", "Thread service is unavailable")
            if not thread_id:
                raise KRDError("thread_required", "thread_id is required for thread view")
            result = await runtime.threads.get(persona_id, thread_id)
            if result is None:
                raise KRDError("thread_not_found", "Thread not found")
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
