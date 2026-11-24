from __future__ import annotations

import copy
from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from krd.models import KRDError
from krd.webapi import export_data, import_commit, import_preview
from .fakes import FakeRuntime


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    yield value
    await value.close()


async def source_export(runtime, persona="persona-a"):
    day = (datetime.now().date() + timedelta(days=1)).isoformat()
    result = await runtime.plans.apply_plan(persona, {"date": day, "title": "可移植计划", "blocks": [{
        "title": "组", "items": [{"title": "未来小项", "schedule": {"type": "exact", "at": "09:00"},
                                  "target": "qq:dm:10001", "interaction": "auto"}],
    }]}, actor="user", expected_revision=0)
    item = result["plan"]["blocks"][0]["items"][0]
    await runtime.plans.record_experience(persona, day, "一段体验", item_id=item["id"])
    return await export_data(runtime, persona)


@pytest.mark.asyncio
async def test_export_excludes_global_weather_cache_and_import_remaps_ids(runtime):
    data = await source_export(runtime)
    await runtime.store.execute(
        "INSERT INTO weather_cache(cache_key,payload_json,fetched_at,expires_at) VALUES('other','{}',0,9999999999)")
    assert "weather_cache" not in data["tables"]
    assert "templates" in data
    preview = await import_preview(runtime, "persona-b", data)
    assert preview["plans"] == 1
    result = await import_commit(runtime, "persona-b", data)
    assert result == {"imported_plans": 1, "skipped_existing": 0, "imported_threads": 0}
    source_plan = data["tables"]["plans"][0]
    imported = await runtime.plans.get_plan_by_date("persona-b", source_plan["date"])
    assert imported["id"] != source_plan["id"] and imported["persona_id"] == "persona-b"
    source_item = data["tables"]["items"][0]
    imported_item = imported["blocks"][0]["items"][0]
    assert imported_item["id"] != source_item["id"]
    experiences = await runtime.plans.experiences("persona-b", source_plan["date"])
    assert experiences[0]["item_id"] == imported_item["id"]
    again = await import_commit(runtime, "persona-b", data)
    assert again == {"imported_plans": 0, "skipped_existing": 1, "imported_threads": 0}


@pytest.mark.asyncio
async def test_historical_import_is_archived_and_never_scheduled(runtime):
    data = await source_export(runtime)
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    data["tables"]["plans"][0]["date"] = yesterday
    data["tables"]["plans"][0]["state"] = "active"
    data["tables"]["day_states"] = []
    data["tables"]["experiences"] = []
    result = await import_commit(runtime, "persona-b", data)
    assert result["imported_plans"] == 1
    plan = await runtime.plans.get_plan_by_date("persona-b", yesterday)
    assert plan["state"] == "archived"
    assert plan["blocks"][0]["items"][0]["state"] == "cancelled"


@pytest.mark.asyncio
async def test_import_rolls_back_all_days_on_later_invalid_item(runtime):
    data = await source_export(runtime)
    second_plan = copy.deepcopy(data["tables"]["plans"][0])
    second_plan["id"] = "pln_second"
    second_plan["date"] = (datetime.now().date() + timedelta(days=2)).isoformat()
    second_block = copy.deepcopy(data["tables"]["blocks"][0])
    second_block["id"], second_block["plan_id"] = "blk_second", "pln_second"
    second_item = copy.deepcopy(data["tables"]["items"][0])
    second_item.update({"id": "itm_second", "plan_id": "pln_second", "block_id": "blk_second", "scheduled_at": 0})
    data["tables"]["plans"].append(second_plan)
    data["tables"]["blocks"].append(second_block)
    data["tables"]["items"].append(second_item)
    with pytest.raises(KRDError):
        await import_commit(runtime, "persona-b", data)
    assert await runtime.store.all("SELECT * FROM plans WHERE persona_id='persona-b'") == []
    assert await runtime.store.all("SELECT * FROM experiences WHERE persona_id='persona-b'") == []
