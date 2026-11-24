from __future__ import annotations

import sqlite3

import pytest

from krd.store import Store


@pytest.mark.asyncio
async def test_v1_database_migrates_additively(tmp_path):
    path = tmp_path / "rhythm.db"
    store = Store(path)
    await store.initialize()
    await store.close()

    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE items DROP COLUMN thread_id")
        connection.execute("ALTER TABLE planning_runs DROP COLUMN required_thread_ids_json")
        connection.execute("ALTER TABLE planning_runs DROP COLUMN response_status")
        connection.execute("DROP TABLE thread_responses")
        connection.execute("DROP TABLE thread_logs")
        connection.execute("DROP TABLE threads")
        connection.execute("PRAGMA user_version=1")
        connection.commit()
    finally:
        connection.close()

    migrated = Store(path)
    await migrated.initialize()
    try:
        item_columns = {row["name"] for row in await migrated.all("PRAGMA table_info(items)")}
        run_columns = {row["name"] for row in await migrated.all("PRAGMA table_info(planning_runs)")}
        assert "thread_id" in item_columns
        assert {"required_thread_ids_json", "response_status"} <= run_columns
        tables = {row["name"] for row in await migrated.all(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"threads", "thread_logs", "thread_responses"} <= tables
        version = await migrated.one("PRAGMA user_version")
        assert version["user_version"] == 2
    finally:
        await migrated.close()
