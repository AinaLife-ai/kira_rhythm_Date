from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
import pytest_asyncio

from krd.hygiene import KRD_TRIGGER, MemoryHygiene
from krd.store import Store


class FakeSessions:
    def __init__(self, chunks):
        self.chunks = chunks

    async def get_session(self, sid, ensure_session=True):
        return SimpleNamespace(content=self.chunks)

    async def update_session(self, sid, content=None):
        self.chunks = content


def chunk(message: str, arguments: str = '{"plans":[]}'):
    return [
        {"role": "user", "content": message},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "rhythm_plan", "arguments": arguments}}]},
        {"role": "tool", "content": "ok"},
    ]


@pytest_asyncio.fixture
async def store(tmp_path):
    value = Store(tmp_path / "rhythm.db")
    await value.initialize()
    yield value
    await value.close()


@pytest.mark.asyncio
async def test_planning_turns_are_summarized_and_chat_is_kept(store):
    await store.execute(
        "INSERT INTO planning_runs(id,trigger_id,persona_id,kind,target_date,session_id,status,"
        "required_thread_ids_json,response_status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ("prn_1", "t", "persona-a", "daily", date.today().isoformat(), "s", "completed",
         "[]", "not_required", "x", 1))
    sessions = FakeSessions([
        chunk(KRD_TRIGGER, '{"plans":[{"items":[1,2,3]}]}'),
        [{"role": "user", "content": "普通聊天"}, {"role": "assistant", "content": "你好"}],
        chunk(KRD_TRIGGER, '{"plans":[{"items":[4,5,6]}]}'),
    ])
    hygiene = MemoryHygiene(SimpleNamespace(session_mgr=sessions), store)
    assert await hygiene.prepare("s", "persona-a") is True
    assert len(sessions.chunks) == 2
    assert sessions.chunks[0][0]["content"] == "普通聊天"
    summary = sessions.chunks[1]
    assert summary[0]["content"] == KRD_TRIGGER
    assert summary[1]["role"] == "assistant"
    assert summary[1]["content"].startswith("[KRD] 上次规划")
    assert "rhythm_plan" not in str(sessions.chunks)


@pytest.mark.asyncio
async def test_memory_hygiene_off_and_mixed_chunks(store):
    await store.execute(
        "UPDATE settings SET value_json=json_set(value_json,'$.memory_hygiene','off') WHERE key='global'")
    sessions = FakeSessions([chunk(KRD_TRIGGER)])
    hygiene = MemoryHygiene(SimpleNamespace(session_mgr=sessions), store)
    assert await hygiene.prepare("s", "persona-a") is False
    assert len(sessions.chunks) == 1

    await store.execute(
        "UPDATE settings SET value_json=json_set(value_json,'$.memory_hygiene','summary') WHERE key='global'")
    mixed = [chunk(KRD_TRIGGER), [{"role": "user", "content": "真实用户"}, {"role": "assistant", "content": "嗯"}]]
    mixed[0].insert(1, {"role": "user", "content": "真实用户也在这批"})
    sessions = FakeSessions(mixed)
    hygiene = MemoryHygiene(SimpleNamespace(session_mgr=sessions), store)
    assert await hygiene.prepare("s", "persona-a") is False
