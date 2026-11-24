from __future__ import annotations

import math

import pytest
import pytest_asyncio

from krd.config import (DEFAULT_EXECUTION_PROMPT, DEFAULT_PLANNING_PROMPT, DEFAULT_REVIEW_PROMPT,
                        LEGACY_EXECUTION_PROMPT, LEGACY_PLANNING_PROMPT, LEGACY_REVIEW_PROMPT, normalized)
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
    {"inject_agenda": "yes"},
    {"agenda_max_chars": 200},
])
@pytest.mark.asyncio
async def test_invalid_nested_config_is_typed_and_not_persisted(store, patch):
    with pytest.raises(KRDError):
        await store.update_config("persona-a", patch, 0)
    assert await store.config_revision("persona-a") == 0
    assert await store.one("SELECT * FROM settings WHERE key='persona:persona-a'") is None


@pytest.mark.asyncio
async def test_agenda_injection_is_hot_configurable(store):
    config, revision = await store.update_config("persona-a", {
        "inject_agenda": False,
        "agenda_max_chars": 800,
    }, 0)
    assert revision == 1
    assert config["inject_agenda"] is False
    assert config["agenda_max_chars"] == 800


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

@pytest.mark.asyncio
async def test_seconds_are_accepted_for_clock_and_windows(store):
    config, _ = await store.update_config("persona-a", {
        "planning_time": "23:00:37",
        "quiet_delivery_windows": [{"start": "23:30:05", "end": "07:00:10"}],
    }, 0)
    assert config["planning_time"] == "23:00:37"
    assert config["quiet_delivery_windows"][0]["end"] == "07:00:10"


def test_legacy_default_prompts_upgrade_without_touching_custom_text():
    migrated = normalized({
        "planning_prompt": LEGACY_PLANNING_PROMPT,
        "execution_prompt": LEGACY_EXECUTION_PROMPT,
        "planning_review": {"prompt": LEGACY_REVIEW_PROMPT},
        "history_char_budget": 12000,
    })
    assert migrated["planning_prompt"] == DEFAULT_PLANNING_PROMPT
    assert migrated["execution_prompt"] == DEFAULT_EXECUTION_PROMPT
    assert migrated["planning_review"]["prompt"] == DEFAULT_REVIEW_PROMPT
    assert migrated["history_char_budget"] == 16000
    assert migrated["threads"]["chat_limit"] == 5
    assert migrated["threads"]["full_dossier_in_planning"] == 5

    custom = normalized({"planning_prompt": "我的自定义规划提示词。", "history_char_budget": 9000})
    assert custom["planning_prompt"] == "我的自定义规划提示词。"
    assert custom["history_char_budget"] == 9000
