from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))
from krd.plans import PlanService
from krd.policy import SessionPolicy
from krd.store import Store


class FakeSessionManager:
    async def get_sessions(self, include_content=False, kind=None):
        return [SimpleNamespace(sid="qq:dm:10001", session_title="陪伴", adapter_name="qq")]


class FakeContext:
    session_mgr = FakeSessionManager()
    adapter_mgr = None


async def main():
    root = Path(tempfile.mkdtemp(prefix="krd-domain-"))
    store = Store(root / "test.db")
    await store.initialize()
    policy = SessionPolicy(store, FakeContext())
    plans = PlanService(store, policy)
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()

    def item(title, hour, identifier=None):
        return {"id": identifier, "title": title, "intent": "保持连续生活", "instruction": "自然行动，也可保持安静",
                "schedule": {"type": "exact", "at": f"{hour:02d}:30"}, "target": "qq:dm:10001"}

    payload = {"date": tomorrow, "title": "从容的一天", "overview": "不排太满", "blocks": [
        {"title": "早晨", "items": [item("早餐", 7), item("阅读", 8)]},
        {"title": "傍晚", "items": [{"title": "随机散步", "schedule": {"type": "window", "start": "18:00", "end": "19:00", "occurrences": 2, "window_mode": "interval_random", "interval_minutes": [5, 15]}, "target": "qq:dm:10001"},
                                   ]},
    ]}
    # Only two exact + two window occurrences = four items.
    created = await plans.apply_many("persona-a", [payload])
    assert created[0]["revision"] == 1
    plan = created[0]["plan"]
    assert sum(len(b["items"]) for b in plan["blocks"]) == 4
    series = [i["series_id"] for b in plan["blocks"] for i in b["items"] if i["series_id"]]
    assert len(series) == 2 and len(set(series)) == 1

    revised_payload = dict(payload)
    revised_payload["expected_revision"] = 1
    revised_payload["overview"] = "留更多空白"
    revised = await plans.apply_plan("persona-a", revised_payload, expected_revision=1)
    assert revised["revision"] == 2
    assert len(revised["plan"]["blocks"]) == 2, revised["plan"]["blocks"]
    assert revised["plan"]["overview"] == "留更多空白"

    state = await plans.set_day_state("persona-a", tomorrow, {"current_appearance": "浅色外套", "current_mood": "安静"}, "bot")
    assert state["current_appearance"] == "浅色外套"
    await plans.record_experience("persona-a", tomorrow, "梦见一座漂浮图书馆", kind="dream")
    dreams = await plans.experiences("persona-a", tomorrow)
    assert dreams[0]["kind"] == "dream"

    # A failure in the second day must roll back the first day too.
    second = datetime.fromisoformat(tomorrow) + timedelta(days=1)
    good = dict(payload, date=second.date().isoformat())
    bad_day = second + timedelta(days=1)
    bad = dict(payload, date=bad_day.date().isoformat())
    bad["blocks"] = [{"title": "错误", "items": [dict(item("太少", 9), execution_probability=0.01)]}]
    try:
        await plans.apply_many("persona-a", [good, bad])
    except Exception:
        pass
    else:
        raise AssertionError("invalid second day unexpectedly passed")
    assert await plans.get_plan_by_date("persona-a", good["date"]) is None
    assert await plans.get_plan_by_date("persona-a", tomorrow) is not None

    # Persona B has a separate life line.
    other = dict(payload, expected_revision=0)
    await plans.apply_plan("persona-b", other)
    assert (await plans.day_state("persona-b", tomorrow))["current_appearance"] != "浅色外套"
    print("DOMAIN SMOKE OK", root)
    await store.close()


asyncio.run(main())
