from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from krd.store import Store


@pytest_asyncio.fixture
async def store(tmp_path):
    value = Store(tmp_path / "test.db")
    await value.initialize()
    yield value
    await value.close()


@pytest.mark.asyncio
async def test_reads_never_observe_uncommitted_other_task_writes(store):
    async with store.transaction() as db:
        await db.execute("INSERT INTO settings(key,value_json,revision,updated_at) VALUES('pending','\"new\"',1,1)")
        reader = asyncio.create_task(store.get_setting("pending", "old"))
        assert await asyncio.wait_for(reader, 1) == "old"
    assert await store.get_setting("pending") == "new"


@pytest.mark.asyncio
async def test_nested_savepoint_rolls_back_only_inner_work(store):
    await store.put_setting("stable", {"value": 1})
    with pytest.raises(ValueError):
        async with store.transaction():
            await store.put_setting("outer", True)
            try:
                async with store.transaction():
                    await store.put_setting("inner", True)
                    raise ValueError("rollback inner")
            except ValueError:
                pass
            assert await store.get_setting("inner") is None
            raise ValueError("rollback outer")
    assert await store.get_setting("stable") == {"value": 1}
    assert await store.get_setting("outer") is None
    assert await store.get_setting("inner") is None
