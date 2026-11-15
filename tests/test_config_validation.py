from __future__ import annotations

import math

import pytest
import pytest_asyncio

from krd.models import KRDError
from krd.store import Store


@pytest_asyncio.fixture
async def store(tmp_path):
    value = Store(tmp_path / "test.db")
    await value.initialize()
    yield value
    await value.close()


@pytest.mark.parametrize("patch", [
    {"enabled": 1},
    {"max_items": True},
    {"history_days": -1},
    {"min_probability": "0.2"},
    {"session_access": None},
    {"execution_pool": None},
    {"execution_pool": {"sessions": [{"sid": "qq:dm:1", "weight": math.nan}]}},
    {"blocked_execution_windows": [{}]},
    {"quiet_delivery_windows": [{"start": "25:00", "end": "07:00"}]},
    {"required_coverage_windows": [{"start": "01:00", "end": "02:00", "min_items": 3, "max_items": 2}]},
    {"planning_time": "24:00"},
    {"timezone": "Not/A_Real_Zone"},
    {"weather": None},
    {"weather": {"mode": "unknown"}},
    {"weather": {"provider": "unknown"}},
    {"weather": {"locations": {"default": {"latitude": 1000, "longitude": 0}}}},
    {"appearance": {"avatar_adapter_order": {}}},
])
@pytest.mark.asyncio
async def test_invalid_nested_config_is_typed_and_not_persisted(store, patch):
    with pytest.raises(KRDError):
        await store.update_config("persona-a", patch, 0)
    assert await store.config_revision("persona-a") == 0
    assert await store.one("SELECT * FROM settings WHERE key='persona:persona-a'") is None


@pytest.mark.asyncio
async def test_valid_nested_override_still_hot_applies(store):
    config, revision = await store.update_config("persona-a", {
        "appearance": {"custom_accent": "#123456"},
        "weather": {"virtual": {"climate": "snow"}},
    }, 0)
    assert revision == 1
    assert config["appearance"]["custom_accent"] == "#123456"
    assert config["weather"]["virtual"]["climate"] == "snow"
    assert config["weather"]["timeout_seconds"] == 3
