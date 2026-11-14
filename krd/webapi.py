from __future__ import annotations

from typing import Any

from .assets import AssetService
from .models import KRDError, now
from .store import dumps, loads


async def bootstrap(runtime, persona_id: str = "") -> dict[str, Any]:
    active = await runtime.active_persona_id()
    persona_id = persona_id or active
    if not persona_id:
        return {"ready": False, "reason": "Create and activate a KiraAI persona first"}
    day = await runtime.plans.current_date(persona_id)
    plan = await runtime.plans.get_plan_by_date(persona_id, day)
    config = await runtime.store.get_config(persona_id)
    banner = None
    banner_id = config["appearance"].get("banner_asset_id")
    if banner_id:
        row = await runtime.store.one("SELECT * FROM assets WHERE persona_id=? AND id=?", (persona_id, banner_id))
        if row:
            banner = runtime.avatars.assets.public(row)
    personas = []
    for persona in await runtime.ctx.persona_mgr.list_personas():
        personas.append({"id": persona.id, "name": persona.name or persona.id, "active": persona.id == active})
    return {
        "ready": True, "persona_id": persona_id, "active_persona_id": active, "personas": personas,
        "date": day, "plan": plan, "day_state": await runtime.plans.day_state(persona_id, day),
        "day_types": await runtime.store.list_day_types(persona_id),
        "config": config, "config_revision": await runtime.store.config_revision(persona_id),
        "global_revision": await runtime.store.config_revision(""),
        "sessions": await runtime.policy.session_options(persona_id, "execution"),
        "planning_sessions": await runtime.policy.session_options(persona_id, "planning"),
        "weather": await runtime.weather.summary(persona_id),
        "avatar": await runtime.avatars.current(persona_id), "banner": banner,
        "scheduler": {"running": runtime.scheduler.running, "next_due": await runtime.scheduler.next_due()},
        "server_time": now(),
    }


async def update_config(runtime, persona_id: str, patch: dict[str, Any], expected_revision: int):
    if "schema_version" in patch or "per_persona" in patch:
        raise KRDError("readonly_config", "schema_version and per_persona are read-only")
    if len(dumps(patch)) > 200000:
        raise KRDError("config_too_large", "Configuration patch exceeds 200 KB")
    config, revision = await runtime.store.update_config(persona_id, patch, expected_revision)
    runtime.scheduler.wake()
    await runtime.broadcast("config_changed", {"persona_id": persona_id, "revision": revision})
    return {"config": config, "revision": revision}


async def export_data(runtime, persona_id: str) -> dict[str, Any]:
    plan_rows = await runtime.store.all("SELECT * FROM plans WHERE persona_id=?", (persona_id,))
    plan_ids = {row["id"] for row in plan_rows}
    tables = {"plans": plan_rows}
    for table in ("blocks", "items", "plan_revisions", "runs", "planning_runs", "day_states", "experiences", "day_types", "session_pools", "mutations", "weather_cache"):
        rows = await runtime.store.all(f"SELECT * FROM {table}")
        if table in {"blocks", "items", "plan_revisions", "runs", "mutations"}:
            rows = [row for row in rows if row.get("plan_id") in plan_ids]
        elif table != "weather_cache":
            rows = [row for row in rows if row.get("persona_id") == persona_id]
        tables[table] = rows
    return {"schema_version": 1, "plugin_id": "kira_rhythm_Date", "persona_id": persona_id,
            "config": await runtime.store.get_config(persona_id), "tables": tables, "exported_at": now()}


async def import_preview(runtime, persona_id: str, data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("tables"), dict):
        raise KRDError("invalid_import", "Expected a KRD schema v1 export")
    plans = data["tables"].get("plans", [])
    if not isinstance(plans, list) or len(plans) > 366:
        raise KRDError("invalid_import", "Invalid plans collection")
    return {"persona_id": persona_id, "plans": len(plans), "day_types": len(data["tables"].get("day_types", [])),
            "include_config": bool(data.get("config")), "warnings": ["Runs are not replayed; only plans and settings are imported."]}


async def import_commit(runtime, persona_id: str, data: dict[str, Any]) -> dict[str, Any]:
    await import_preview(runtime, persona_id, data)
    if data.get("config"):
        imported_config = dict(data["config"])
        imported_config.pop("schema_version", None)
        imported_config.pop("per_persona", None)
        await update_config(runtime, persona_id, imported_config, await runtime.store.config_revision(persona_id))
    for entry in data["tables"].get("day_types", []):
        await runtime.store.save_day_type(persona_id, entry)
    imported = 0
    for row in data["tables"].get("plans", []):
        plan = await runtime.plans.get_plan_by_date(persona_id, row["date"])
        if plan:
            continue
        payload = {key: row[key] for key in ("date", "title", "overview", "planned_appearance", "planned_mood")}
        blocks = [block for block in data["tables"].get("blocks", []) if block["plan_id"] == row["id"]]
        payload["blocks"] = []
        for block in blocks:
            items = [item for item in data["tables"].get("items", []) if item["block_id"] == block["id"]]
            payload["blocks"].append({**block, "items": [{**item, "schedule": loads(item["schedule_json"], {})} for item in items]})
        await runtime.plans.apply_plan(persona_id, payload, actor="user", expected_revision=0)
        imported += 1
    runtime.scheduler.wake()
    return {"imported_plans": imported}


async def diagnostics(runtime) -> dict[str, Any]:
    counts = {}
    for table in ("plans", "items", "runs", "planning_runs", "day_states", "experiences", "assets"):
        row = await runtime.store.one(f"SELECT COUNT(*) AS count FROM {table}")
        counts[table] = row["count"]
    return {"scheduler": {"running": runtime.scheduler.running, "next_due": await runtime.scheduler.next_due()},
            "counts": counts, "database": "SQLite WAL", "websocket_clients": len(runtime.ws_clients)}


def asset_service(runtime) -> AssetService:
    return runtime.avatars.assets
