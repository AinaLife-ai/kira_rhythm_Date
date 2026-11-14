from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

from .config import BUILTIN_DAY_TYPES, deep_merge, normalized
from .models import KRDError, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, value_json TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY, persona_id TEXT NOT NULL, date TEXT NOT NULL, day_type_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '', overview TEXT NOT NULL DEFAULT '', planned_appearance TEXT NOT NULL DEFAULT '',
    planned_mood TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'active', revision INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL DEFAULT 'bot', created_at REAL NOT NULL, updated_at REAL NOT NULL,
    UNIQUE(persona_id, date)
);
CREATE INDEX IF NOT EXISTS plans_persona_date ON plans(persona_id, date);
CREATE TABLE IF NOT EXISTS blocks (
    id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, title TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,
    color TEXT NOT NULL DEFAULT '', cover_asset_id TEXT NOT NULL DEFAULT '', meta_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS blocks_plan ON blocks(plan_id, position);
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, block_id TEXT NOT NULL, series_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL, intent TEXT NOT NULL DEFAULT '', instruction TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0, schedule_json TEXT NOT NULL, scheduled_at REAL NOT NULL,
    target TEXT NOT NULL, interaction TEXT NOT NULL DEFAULT 'auto', category TEXT NOT NULL DEFAULT '',
    execution_probability REAL NOT NULL DEFAULT 1.0, state TEXT NOT NULL DEFAULT 'scheduled',
    revision INTEGER NOT NULL DEFAULT 1, reason TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE,
    FOREIGN KEY(block_id) REFERENCES blocks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS items_due ON items(state, scheduled_at);
CREATE INDEX IF NOT EXISTS items_plan ON items(plan_id, state, position);
CREATE TABLE IF NOT EXISTS plan_revisions (
    plan_id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot_json TEXT NOT NULL, diff_json TEXT NOT NULL,
    actor TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL,
    PRIMARY KEY(plan_id, revision), FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, item_id TEXT NOT NULL, plan_id TEXT NOT NULL, persona_id TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1, event_id TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'item', status TEXT NOT NULL DEFAULT 'prepared', scheduled_at REAL NOT NULL,
    claimed_at REAL, responded_at REAL, finalized_at REAL, probability REAL, draw REAL,
    error TEXT NOT NULL DEFAULT '', input_tokens INTEGER, output_tokens INTEGER, raw_output TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS runs_attempt ON runs(item_id, scheduled_at, attempt);
CREATE INDEX IF NOT EXISTS runs_item ON runs(item_id, status, claimed_at);
CREATE TABLE IF NOT EXISTS planning_runs (
    id TEXT PRIMARY KEY, trigger_id TEXT UNIQUE NOT NULL, persona_id TEXT NOT NULL, kind TEXT NOT NULL,
    target_date TEXT NOT NULL, session_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
    reason TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, finished_at REAL, error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS planning_persona ON planning_runs(persona_id, status, created_at);
CREATE TABLE IF NOT EXISTS day_states (
    persona_id TEXT NOT NULL, date TEXT NOT NULL, current_appearance TEXT NOT NULL DEFAULT '',
    current_mood TEXT NOT NULL DEFAULT '', current_location TEXT NOT NULL DEFAULT '',
    current_activity TEXT NOT NULL DEFAULT '', current_note TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'bot', updated_at REAL NOT NULL,
    PRIMARY KEY(persona_id, date)
);
CREATE TABLE IF NOT EXISTS experiences (
    id TEXT PRIMARY KEY, persona_id TEXT NOT NULL, date TEXT NOT NULL, item_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'note', content TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS experiences_persona ON experiences(persona_id, date, created_at);
CREATE TABLE IF NOT EXISTS day_types (
    id TEXT NOT NULL, persona_id TEXT NOT NULL, name TEXT NOT NULL, rules_json TEXT NOT NULL DEFAULT '{}',
    config_json TEXT NOT NULL DEFAULT '{}', builtin INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(persona_id, id), UNIQUE(persona_id, name)
);
CREATE TABLE IF NOT EXISTS session_pools (
    id TEXT NOT NULL, persona_id TEXT NOT NULL, kind TEXT NOT NULL, members_json TEXT NOT NULL DEFAULT '[]',
    strategy TEXT NOT NULL DEFAULT 'pure_random', state_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(id, persona_id, kind)
);
CREATE TABLE IF NOT EXISTS mutations (
    id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, item_id TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL,
    actor TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', units INTEGER NOT NULL DEFAULT 0,
    operation TEXT NOT NULL, before_json TEXT NOT NULL DEFAULT '', after_json TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS mutations_budget ON mutations(actor, created_at, units);
CREATE TABLE IF NOT EXISTS weather_cache (
    cache_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, fetched_at REAL NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY, persona_id TEXT NOT NULL, hash TEXT NOT NULL, path TEXT NOT NULL,
    mime TEXT NOT NULL, width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0,
    size INTEGER NOT NULL DEFAULT 0, ref_count INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
    UNIQUE(persona_id, hash)
);
"""


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str, fallback: Any = None) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.db: aiosqlite.Connection | None = None
        self.write_lock = asyncio.Lock()
        self._tx_state: ContextVar[tuple[aiosqlite.Connection, int] | None] = ContextVar("krd_tx_state", default=None)

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path, timeout=10)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA synchronous=NORMAL")
        await self.db.execute("PRAGMA foreign_keys=ON")
        await self.db.execute("PRAGMA busy_timeout=10000")
        await self.db.executescript(SCHEMA)
        async with self.transaction() as db:
            await db.execute("PRAGMA user_version=1")
            await db.execute(
                "INSERT OR IGNORE INTO settings(key,value_json,revision,updated_at) VALUES('global',?,1,?)",
                (dumps(normalized({})), now()),
            )

    async def close(self) -> None:
        if self.db is not None:
            await self.db.close()
            self.db = None

    def require_db(self) -> aiosqlite.Connection:
        if self.db is None:
            raise RuntimeError("KRD store is not initialized")
        return self.db

    @asynccontextmanager
    async def transaction(self):
        current = self._tx_state.get()
        if current and current[0] is self.db:
            db, depth = current
            savepoint = f"krd_sp_{depth}"
            await db.execute(f"SAVEPOINT {savepoint}")
            token = self._tx_state.set((db, depth + 1))
            try:
                yield db
                await db.execute(f"RELEASE SAVEPOINT {savepoint}")
            except BaseException:
                await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                await db.execute(f"RELEASE SAVEPOINT {savepoint}")
                raise
            finally:
                self._tx_state.reset(token)
            return
        async with self.write_lock:
            db = self.require_db()
            await db.execute("BEGIN IMMEDIATE")
            token = self._tx_state.set((db, 0))
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise
            finally:
                self._tx_state.reset(token)

    async def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        async with self.require_db().execute(sql, tuple(params)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        async with self.require_db().execute(sql, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        async with self.transaction() as db:
            await db.execute(sql, tuple(params))

    async def get_setting(self, key: str, default: Any = None) -> Any:
        row = await self.one("SELECT value_json FROM settings WHERE key=?", (key,))
        return loads(row["value_json"], default) if row else default

    async def put_setting(self, key: str, value: Any) -> None:
        await self.execute(
            "INSERT INTO settings(key,value_json,revision,updated_at) VALUES(?,?,1,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,revision=settings.revision+1,updated_at=excluded.updated_at",
            (key, dumps(value), now()),
        )

    async def get_config(self, persona_id: str) -> dict[str, Any]:
        global_row = await self.one("SELECT value_json FROM settings WHERE key='global'")
        base = normalized(loads(global_row["value_json"], {}) if global_row else {})
        if persona_id:
            row = await self.one("SELECT value_json FROM settings WHERE key=?", (f"persona:{persona_id}",))
            if row:
                base = normalized(deep_merge(base, loads(row["value_json"], {})))
        return base

    async def update_config(self, persona_id: str, patch: dict[str, Any], expected_revision: int) -> tuple[dict[str, Any], int]:
        key = "global" if not persona_id else f"persona:{persona_id}"
        async with self.transaction() as db:
            async with db.execute("SELECT value_json,revision FROM settings WHERE key=?", (key,)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                if expected_revision not in (0, 1):
                    raise KRDError("config_conflict", "Configuration was changed concurrently")
                current, revision = {}, 0
            else:
                current, revision = loads(row["value_json"], {}), row["revision"]
                if revision != expected_revision:
                    raise KRDError("config_conflict", "Configuration was changed concurrently", current_revision=revision)
            if persona_id:
                base = await self.get_config("") if key != "global" else current
                updated = normalized(deep_merge(base, deep_merge(current, patch)))
                # Persist only the override patch relative to the current global config.
                persisted = deep_merge(current, patch)
            else:
                updated = normalized(deep_merge(current, patch))
                persisted = updated
            next_revision = revision + 1
            await db.execute(
                "INSERT INTO settings(key,value_json,revision,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,revision=excluded.revision,updated_at=excluded.updated_at",
                (key, dumps(persisted), next_revision, now()),
            )
        return updated, next_revision

    async def config_revision(self, persona_id: str = "") -> int:
        key = "global" if not persona_id else f"persona:{persona_id}"
        row = await self.one("SELECT revision FROM settings WHERE key=?", (key,))
        return int(row["revision"]) if row else 0

    async def ensure_persona(self, persona_id: str) -> None:
        if not persona_id:
            return
        async with self.transaction() as db:
            for entry in BUILTIN_DAY_TYPES:
                await db.execute(
                    "INSERT OR IGNORE INTO day_types(id,persona_id,name,rules_json,config_json,builtin) VALUES(?,?,?,?,?,1)",
                    (entry["id"], persona_id, entry["name"], "{}", dumps({"color": entry["color"]})),
                )

    async def list_day_types(self, persona_id: str) -> list[dict[str, Any]]:
        await self.ensure_persona(persona_id)
        rows = await self.all("SELECT * FROM day_types WHERE persona_id=? ORDER BY builtin DESC,name", (persona_id,))
        return [{**row, "rules": loads(row.pop("rules_json"), {}), "config": loads(row.pop("config_json"), {})} for row in rows]

    async def save_day_type(self, persona_id: str, entry: dict[str, Any]) -> None:
        name = str(entry.get("name", "")).strip()
        identifier = str(entry.get("id", "")).strip()
        if not name or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,79}", identifier):
            raise KRDError("invalid_day_type", "Day type ID must use letters, digits, underscore or hyphen")
        if len(name) > 80 or len(dumps(entry)) > 200000:
            raise KRDError("invalid_day_type", "Day type name or configuration is too large")
        await self.ensure_persona(persona_id)
        await self.execute(
            "INSERT INTO day_types(id,persona_id,name,rules_json,config_json,builtin) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(persona_id,id) DO UPDATE SET name=excluded.name,rules_json=excluded.rules_json,config_json=excluded.config_json",
            (identifier, persona_id, name, dumps(entry.get("rules", {})), dumps(entry.get("config", {})), int(bool(entry.get("builtin", False)))),
        )

    async def delete_day_type(self, persona_id: str, identifier: str) -> None:
        row = await self.one("SELECT builtin FROM day_types WHERE persona_id=? AND id=?", (persona_id, identifier))
        if row is None:
            raise KRDError("not_found", "Day type not found")
        if row["builtin"]:
            raise KRDError("builtin_day_type", "Built-in day types cannot be deleted")
        used = await self.one("SELECT 1 AS used FROM plans WHERE persona_id=? AND day_type_id=? LIMIT 1", (persona_id, identifier))
        if used:
            raise KRDError("day_type_in_use", "This day type is still used by a plan")
        await self.execute("DELETE FROM day_types WHERE persona_id=? AND id=?", (persona_id, identifier))

    async def pool_state(self, persona_id: str, kind: str) -> dict[str, Any]:
        return await self.get_setting(f"selection:{persona_id}:{kind}", {})

    async def save_pool_state(self, persona_id: str, kind: str, state: dict[str, Any]) -> None:
        await self.put_setting(f"selection:{persona_id}:{kind}", state)
