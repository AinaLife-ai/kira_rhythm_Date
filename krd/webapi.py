from __future__ import annotations

from typing import Any

from .assets import AssetService
from .models import ACTIVE_ITEM_STATES, KRDError, TERMINAL_ITEM_STATES, new_id, now
from .timeutils import parse_date
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
        # Initial paint never waits for a remote weather provider. The frontend
        # starts the normal TTL-coalesced refresh after applying this snapshot.
        "weather": await runtime.weather.summary(persona_id, allow_network=False),
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
    for table in ("blocks", "items", "plan_revisions", "runs", "planning_runs", "day_states", "experiences", "day_types", "session_pools", "mutations"):
        rows = await runtime.store.all(f"SELECT * FROM {table}")
        if table in {"blocks", "items", "plan_revisions", "runs", "mutations"}:
            rows = [row for row in rows if row.get("plan_id") in plan_ids]
        else:
            rows = [row for row in rows if row.get("persona_id") == persona_id]
        tables[table] = rows
    return {"schema_version": 1, "plugin_id": "kira_rhythm_Date", "persona_id": persona_id,
            "config": await runtime.store.get_config(persona_id),
            "templates": await runtime.store.get_setting(f"templates:{persona_id}", []),
            "tables": tables, "exported_at": now()}


async def import_preview(runtime, persona_id: str, data: dict[str, Any]) -> dict[str, Any]:
    if (not isinstance(data, dict) or data.get("schema_version") != 1 or
            data.get("plugin_id") != "kira_rhythm_Date" or not isinstance(data.get("tables"), dict)):
        raise KRDError("invalid_import", "Expected a KRD schema v1 export")
    if len(dumps(data)) > 20_000_000:
        raise KRDError("invalid_import", "Import file exceeds 20 MB")
    tables = data["tables"]
    limits = {"plans": 366, "blocks": 5000, "items": 50000, "day_types": 500,
              "day_states": 5000, "experiences": 50000}
    for table, maximum in limits.items():
        rows = tables.get(table, [])
        if not isinstance(rows, list) or len(rows) > maximum:
            raise KRDError("invalid_import", f"Invalid or oversized {table} collection")
    plans = tables["plans"]
    return {"persona_id": persona_id, "plans": len(plans), "day_types": len(tables["day_types"]),
            "include_config": bool(data.get("config")),
            "warnings": ["Runs are not replayed. Historical plans are archived; ambiguous active states are cancelled."]}


async def import_commit(runtime, persona_id: str, data: dict[str, Any]) -> dict[str, Any]:
    await import_preview(runtime, persona_id, data)
    tables = data["tables"]
    plans, blocks, items = tables["plans"], tables["blocks"], tables["items"]
    source_plan_ids = [str(row.get("id", "")) for row in plans]
    source_block_ids = [str(row.get("id", "")) for row in blocks]
    source_item_ids = [str(row.get("id", "")) for row in items]
    if (not all(source_plan_ids + source_block_ids + source_item_ids) or
            len(source_plan_ids) != len(set(source_plan_ids)) or
            len(source_block_ids) != len(set(source_block_ids)) or
            len(source_item_ids) != len(set(source_item_ids))):
        raise KRDError("invalid_import", "Import contains missing or duplicate object IDs")
    plan_ids = {old: new_id("pln") for old in source_plan_ids}
    block_ids = {old: new_id("blk") for old in source_block_ids}
    item_ids = {old: new_id("itm") for old in source_item_ids}
    imported_items = set()
    imported = skipped = 0
    timestamp = now()
    today = await runtime.plans.current_date(persona_id)
    blocks_by_plan: dict[str, list[dict]] = {}
    for block in blocks:
        blocks_by_plan.setdefault(str(block.get("plan_id", "")), []).append(block)
    items_by_block: dict[str, list[dict]] = {}
    for item in items:
        items_by_block.setdefault(str(item.get("block_id", "")), []).append(item)
    async with runtime.store.transaction() as db:
        if data.get("config"):
            imported_config = dict(data["config"])
            imported_config.pop("schema_version", None)
            imported_config.pop("per_persona", None)
            await runtime.store.update_config(persona_id, imported_config, await runtime.store.config_revision(persona_id))
        for entry in tables["day_types"]:
            await runtime.store.save_day_type(persona_id, entry)
        for row in plans:
            day = parse_date(str(row.get("date", ""))).isoformat()
            if await runtime.plans.get_plan_by_date(persona_id, day):
                skipped += 1
                continue
            old_plan_id = str(row["id"])
            plan_id = plan_ids[old_plan_id]
            historical = day < today
            plan_state = "archived" if historical else str(row.get("state", "active"))
            if plan_state not in {"active", "draft", "archived"}:
                raise KRDError("invalid_import", "Unknown plan state")
            await db.execute(
                "INSERT INTO plans(id,persona_id,date,day_type_id,title,overview,planned_appearance,planned_mood,state,revision,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,1,'user',?,?)",
                (plan_id, persona_id, day, str(row.get("day_type_id", "weekday")), str(row.get("title", "这一天"))[:160],
                 str(row.get("overview", ""))[:3000], str(row.get("planned_appearance", ""))[:1000],
                 str(row.get("planned_mood", ""))[:1000], plan_state, timestamp, timestamp))
            for block in blocks_by_plan.get(old_plan_id, []):
                old_block_id = str(block["id"])
                block_id = block_ids[old_block_id]
                meta = loads(block.get("meta_json"), {}) if isinstance(block.get("meta_json"), str) else block.get("meta", {})
                if not isinstance(meta, dict):
                    raise KRDError("invalid_import", "Block metadata must be an object")
                await db.execute(
                    "INSERT INTO blocks(id,plan_id,title,position,color,cover_asset_id,meta_json) VALUES(?,?,?,?,?,?,?)",
                    (block_id, plan_id, str(block.get("title", "生活片段"))[:120], int(block.get("position", 0)),
                     str(block.get("color", ""))[:32], "", dumps(meta)))
                for item in items_by_block.get(old_block_id, []):
                    old_item_id = str(item["id"])
                    item_id = item_ids[old_item_id]
                    schedule = loads(item.get("schedule_json"), {}) if isinstance(item.get("schedule_json"), str) else item.get("schedule", {})
                    if not isinstance(schedule, dict):
                        raise KRDError("invalid_import", "Item schedule must be an object")
                    scheduled_at = float(item.get("scheduled_at", 0))
                    if scheduled_at <= 0:
                        raise KRDError("invalid_import", "Item scheduled_at is invalid")
                    state = str(item.get("state", "scheduled"))
                    if state not in ACTIVE_ITEM_STATES | TERMINAL_ITEM_STATES | {"failed", "interrupted"}:
                        raise KRDError("invalid_import", "Unknown item state")
                    if historical and state not in TERMINAL_ITEM_STATES:
                        state = "cancelled"
                    elif state in {"queued", "running"}:
                        state = "scheduled"
                    await db.execute(
                        "INSERT INTO items(id,plan_id,block_id,series_id,title,intent,instruction,position,schedule_json,scheduled_at,target,interaction,category,execution_probability,state,revision,reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
                        (item_id, plan_id, block_id, new_id("ser") if item.get("series_id") else "",
                         str(item.get("title", "未命名生活小项"))[:160], str(item.get("intent", ""))[:1000],
                         str(item.get("instruction", ""))[:6000], int(item.get("position", 0)), dumps(schedule), scheduled_at,
                         str(item.get("target", "")), str(item.get("interaction", "auto")), str(item.get("category", ""))[:60],
                         float(item.get("execution_probability", 1)), state, str(item.get("reason", ""))[:1000], timestamp, timestamp))
                    imported_items.add(old_item_id)
            await db.execute(
                "INSERT INTO plan_revisions(plan_id,revision,snapshot_json,diff_json,actor,reason,created_at) VALUES(?,?,?,?,?,?,?)",
                (plan_id, 1, dumps({"plan": {"id": plan_id, "date": day, "revision": 1}, "imported": True}),
                 "[]", "user", "Imported from KRD backup", timestamp))
            imported += 1
        for state in tables["day_states"]:
            day = parse_date(str(state.get("date", ""))).isoformat()
            await db.execute(
                "INSERT OR IGNORE INTO day_states(persona_id,date,current_appearance,current_mood,current_location,current_activity,current_note,revision,source,updated_at) VALUES(?,?,?,?,?,?,?,1,'import',?)",
                (persona_id, day, str(state.get("current_appearance", ""))[:2000], str(state.get("current_mood", ""))[:2000],
                 str(state.get("current_location", ""))[:2000], str(state.get("current_activity", ""))[:2000],
                 str(state.get("current_note", ""))[:2000], timestamp))
        for experience in tables["experiences"]:
            old_item = str(experience.get("item_id", ""))
            await db.execute(
                "INSERT INTO experiences(id,persona_id,date,item_id,kind,content,created_at) VALUES(?,?,?,?,?,?,?)",
                (new_id("exp"), persona_id, parse_date(str(experience.get("date", ""))).isoformat(),
                 item_ids.get(old_item, "") if old_item in imported_items else "", str(experience.get("kind", "note"))[:40],
                 str(experience.get("content", ""))[:8000], float(experience.get("created_at", timestamp))))
        templates = data.get("templates", [])
        if not isinstance(templates, list) or len(templates) > 100 or len(dumps(templates)) > 2_000_000:
            raise KRDError("invalid_import", "Invalid templates collection")
        if templates:
            await runtime.store.put_setting(f"templates:{persona_id}", templates)
    runtime.scheduler.wake()
    await runtime.broadcast("data_changed", {"persona_id": persona_id, "source": "import"})
    return {"imported_plans": imported, "skipped_existing": skipped}


async def diagnostics(runtime) -> dict[str, Any]:
    counts = {}
    for table in ("plans", "items", "runs", "planning_runs", "day_states", "experiences", "assets"):
        row = await runtime.store.one(f"SELECT COUNT(*) AS count FROM {table}")
        counts[table] = row["count"]
    return {"scheduler": {"running": runtime.scheduler.running, "next_due": await runtime.scheduler.next_due()},
            "counts": counts, "database": "SQLite WAL", "websocket_clients": len(runtime.ws_clients)}


def asset_service(runtime) -> AssetService:
    return runtime.avatars.assets
