from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Any

from core.chat import Group, KiraIMMessage, KiraMessageBatchEvent, MessageChain, Session, User
from core.chat.message_elements import Text

from .context import ContextBuilder
from .models import KRDError, new_id, now
from .policy import SessionPolicy
from .plans import PlanService
from .store import Store
from .timeutils import next_daily, timezone, to_utc


class Scheduler:
    def __init__(self, runtime):
        self.runtime = runtime
        self.store: Store = runtime.store
        self.plans: PlanService = runtime.plans
        self.policy: SessionPolicy = runtime.policy
        self.ctx = runtime.ctx
        self.rng = random.Random()
        self.wake_event = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.running = False

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        await self.recover()
        self.task = asyncio.create_task(self._loop(), name="krd_scheduler")

    async def stop(self) -> None:
        self.running = False
        self.wake_event.set()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    def wake(self) -> None:
        self.wake_event.set()

    async def recover(self) -> None:
        rows = await self.store.all("SELECT id,item_id,status FROM runs WHERE status IN ('prepared','queued','running')")
        for row in rows:
            await self.store.execute("UPDATE runs SET status='interrupted',finalized_at=?,error='Interrupted before confirmed response' WHERE id=?", (now(), row["id"]))
            await self.store.execute("UPDATE items SET state='interrupted',updated_at=? WHERE id=? AND state IN ('queued','running')", (now(), row["item_id"]))

    async def _loop(self) -> None:
        while self.running:
            try:
                await self.dispatch_due()
                due = await self.next_due()
                timeout = None if due is None else max(0.05, min(due - time.time(), 3600))
                try:
                    await asyncio.wait_for(self.wake_event.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    pass
                self.wake_event.clear()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.runtime.log("error", "scheduler_loop", error=str(exc))
                try:
                    await asyncio.wait_for(self.wake_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                self.wake_event.clear()

    async def next_due(self) -> float | None:
        persona_id = await self.runtime.active_persona_id()
        if not persona_id:
            return None
        config = await self.store.get_config(persona_id)
        if not config["enabled"]:
            return None
        candidates = []
        row = await self.store.one(
            "SELECT MIN(i.scheduled_at) AS due FROM items i JOIN plans p ON p.id=i.plan_id "
            "WHERE p.persona_id=? AND p.state='active' AND i.state='scheduled'", (persona_id,))
        if row and row["due"] is not None:
            candidates.append(float(row["due"]))
        if config["auto_plan"]:
            due = next_daily(time.time(), config["planning_time"], self.policy.timezone_name(config))
            trigger_id = f"daily:{persona_id}:{datetime.fromtimestamp(due, timezone(self.policy.timezone_name(config))).isoformat()}"
            exists = await self.store.one("SELECT id FROM planning_runs WHERE trigger_id=?", (trigger_id,))
            if not exists:
                candidates.append(due)
        return min(candidates) if candidates else None

    async def dispatch_due(self) -> None:
        persona_id = await self.runtime.active_persona_id()
        if not persona_id:
            return
        config = await self.store.get_config(persona_id)
        if not config["enabled"]:
            return
        rows = await self.store.all(
            "SELECT i.* FROM items i JOIN plans p ON p.id=i.plan_id WHERE p.persona_id=? AND p.state='active' "
            "AND i.state='scheduled' AND i.scheduled_at<=? ORDER BY i.scheduled_at LIMIT 100",
            (persona_id, time.time()))
        for row in rows:
            await self.claim_item(row["id"])
        if config["auto_plan"]:
            today = datetime.now(timezone(self.policy.timezone_name(config))).date().isoformat()
            due = to_utc(today, config["planning_time"], self.policy.timezone_name(config))
            if due <= time.time():
                trigger_id = f"daily:{persona_id}:{datetime.fromtimestamp(due, timezone(self.policy.timezone_name(config))).isoformat()}"
                target = await self.next_missing_date(persona_id)
                await self.trigger_planning(persona_id, "daily", target, "Scheduled daily planning", trigger_id)

    async def next_missing_date(self, persona_id: str) -> str:
        config = await self.store.get_config(persona_id)
        current = datetime.fromisoformat(await self.plans.current_date(persona_id)) + timedelta(days=1)
        # An existing next-day plan is the object of this revision opportunity;
        # do not skip it merely because it already exists.
        if await self.plans.get_plan_by_date(persona_id, current.date().isoformat()):
            return current.date().isoformat()
        if config["planning_mode"] == "tomorrow":
            return current.date().isoformat()
        for offset in range(config["max_horizon_days"]):
            day = current + timedelta(days=offset)
            if not await self.plans.get_plan_by_date(persona_id, day.date().isoformat()):
                return day.date().isoformat()
        return current.date().isoformat()

    async def claim_item(self, item_id: str, manual: bool = False) -> dict[str, Any] | None:
        timestamp = time.time()
        async with self.store.transaction() as db:
            async with db.execute(
                "SELECT i.*,p.persona_id,p.state AS plan_state FROM items i JOIN plans p ON p.id=i.plan_id WHERE i.id=?",
                (item_id,)) as cursor:
                row = await cursor.fetchone()
                item = dict(row) if row else None
            if not item or item["plan_state"] != "active" or item["state"] != "scheduled":
                return None
            config = await self.store.get_config(item["persona_id"])
            if not manual and timestamp > item["scheduled_at"] + config["recovery_grace_seconds"]:
                await db.execute("UPDATE items SET state='missed',updated_at=? WHERE id=?", (timestamp, item_id))
                return None
            probability = 1.0 if manual else float(item["execution_probability"])
            draw = self.rng.random()
            skipped = draw >= probability
            state = "skipped_probability" if skipped else "queued"
            await db.execute("UPDATE items SET state=?,updated_at=? WHERE id=? AND state='scheduled'", (state, timestamp, item_id))
            async with db.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM runs WHERE item_id=?", (item_id,)) as cursor:
                attempt = (await cursor.fetchone())[0]
            run = {
                "id": new_id("run"), "item_id": item_id, "plan_id": item["plan_id"], "persona_id": item["persona_id"],
                "attempt": attempt, "session_id": item["target"], "kind": "item",
                "status": "skipped_probability" if skipped else "prepared", "scheduled_at": timestamp if manual else item["scheduled_at"],
                "claimed_at": timestamp, "probability": probability, "draw": draw,
            }
            await db.execute(
                "INSERT INTO runs(id,item_id,plan_id,persona_id,attempt,session_id,kind,status,scheduled_at,claimed_at,probability,draw) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(run[key] for key in ("id", "item_id", "plan_id", "persona_id", "attempt", "session_id", "kind", "status", "scheduled_at", "claimed_at", "probability", "draw")))
        if run["status"] == "prepared":
            await self.publish_run(run)
        await self.runtime.broadcast("item_changed", {"item_id": item_id, "state": state})
        if not manual:
            await self.check_all_triggered(item["plan_id"])
        return run

    async def trigger_planning(self, persona_id: str, kind: str, target_date: str, reason: str,
                               trigger_id: str | None = None) -> dict[str, Any] | None:
        if not persona_id or persona_id != await self.runtime.active_persona_id():
            return None
        config = await self.store.get_config(persona_id)
        if not config["enabled"] or (kind != "manual" and not config["auto_plan"]):
            return None
        trigger_id = trigger_id or new_id(f"trg_{kind}")
        existing = await self.store.one("SELECT * FROM planning_runs WHERE trigger_id=?", (trigger_id,))
        if existing:
            return existing
        target = await self.policy.require_target(persona_id, "", "planning")
        if not target:
            return None
        run = {"id": new_id("prn"), "trigger_id": trigger_id, "persona_id": persona_id, "kind": kind,
               "target_date": target_date, "session_id": target, "status": "prepared", "reason": reason}
        await self.store.execute(
            "INSERT INTO planning_runs(id,trigger_id,persona_id,kind,target_date,session_id,status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (run["id"], trigger_id, persona_id, kind, target_date, target, "prepared", reason, now()))
        await self.publish_run(run)
        return run

    async def publish_run(self, run: dict[str, Any]) -> None:
        kind = run["kind"]
        run_id = run["id"]
        target = run["session_id"]
        try:
            allowed, reason = await self.policy.check_adapter_permission(target)
            if not allowed:
                raise KRDError(reason, f"Cannot dispatch to {target}: {reason}")
            resolver = getattr(self.ctx.session_mgr, "resolve_session", None)
            if resolver is not None:
                session = await resolver(target)
            else:
                parts = target.split(":", 2)
                session = Session(adapter_name=parts[0], session_type=parts[1], session_id=parts[2])
            parts = target.split(":", 2)
            adapter = self.ctx.adapter_mgr.get_adapter(parts[0])
            if adapter is None:
                raise KRDError("adapter_offline", f"Adapter not found: {parts[0]}")
            supported = await self.policy.supported_elements(parts[0])
            adapter_config = getattr(adapter, "config", {}) or {}
            self_id = str(adapter_config.get("self_id") or adapter_config.get("bot_pid") or getattr(adapter, "self_id", "") or "unknown")
            persona_id = run["persona_id"]
            metadata = {"run_id": run_id, "kind": kind, "persona_id": persona_id}
            if kind == "item":
                metadata.update({"item_id": run["item_id"], "plan_id": run["plan_id"], "date": ""})
            else:
                metadata.update({"item_id": "", "plan_id": "", "date": run["target_date"], "trigger_id": run["trigger_id"]})
            message = KiraIMMessage(
                message_id=f"krd:{run_id}", self_id=self_id,
                chain=MessageChain([Text("[生活节律｜系统触发]\n")]), timestamp=int(time.time()),
                sender=User(user_id="system_krd", nickname="生活节律"),
                group=Group(group_id=session.session_id) if session.session_type == "gm" else None,
                is_notice=True, is_mentioned=True, extra={"krd": metadata},
            )
            event = KiraMessageBatchEvent(
                supported_elements=supported, timestamp=int(time.time()), adapter=adapter.info,
                session=session, messages=[message], extra={"krd_batch": True},
            )
            if kind == "item":
                await self.store.execute("UPDATE runs SET status='queued',event_id=? WHERE id=?", (event.event_id, run_id))
            else:
                await self.store.execute("UPDATE planning_runs SET status='queued' WHERE id=?", (run_id,))
            await self.ctx.event_bus.publish(event)
            await self.runtime.broadcast("run_queued", {"run_id": run_id, "kind": kind})
        except Exception as exc:
            if kind == "item":
                await self.store.execute("UPDATE runs SET status='failed',error=? WHERE id=?", (str(exc), run_id))
                await self.store.execute("UPDATE items SET state='failed',updated_at=? WHERE id=?", (now(), run["item_id"]))
            else:
                await self.store.execute("UPDATE planning_runs SET status='failed',error=?,finished_at=? WHERE id=?", (str(exc), now(), run_id))
            self.runtime.log("warning", "dispatch_failed", run_id=run_id, error=str(exc))

    async def on_request(self, event) -> None:
        for metadata in ContextBuilder.metadata(event):
            if metadata["kind"] == "item":
                await self.store.execute("UPDATE runs SET status='running' WHERE id=? AND status IN ('prepared','queued')", (metadata["run_id"],))
            else:
                await self.store.execute("UPDATE planning_runs SET status='running' WHERE id=? AND status IN ('prepared','queued')", (metadata["run_id"],))

    async def on_response(self, event, response) -> None:
        text = str(getattr(response, "text_response", "") or "")
        has_tool_calls = bool(getattr(response, "tool_calls", None))
        silent = self.is_silent(text) and not has_tool_calls
        status = getattr(response, "status", "success")
        active_persona = await self.runtime.active_persona_id()
        for metadata in ContextBuilder.metadata(event):
            if metadata["persona_id"] != active_persona:
                continue
            run_id = metadata["run_id"]
            if metadata["kind"] == "item":
                run = await self.store.one("SELECT * FROM runs WHERE id=?", (run_id,))
                if not run:
                    continue
                item = await self.store.one("SELECT * FROM items WHERE id=?", (run["item_id"],))
                if not item:
                    continue
                if status == "error":
                    await self.store.execute("UPDATE runs SET status='failed',responded_at=?,raw_output=?,error=? WHERE id=?",
                                             (now(), text, "model_error", run_id))
                    await self.store.execute("UPDATE items SET state='failed',updated_at=? WHERE id=?", (now(), item["id"]))
                    state = "failed"
                else:
                    state = "triggered_silent" if silent or item["interaction"] == "silent" else "triggered"
                    error = "delivery_unmet" if item["interaction"] == "must_message" and silent else ""
                    await self.store.execute(
                        "UPDATE runs SET status='responded',responded_at=?,raw_output=?,input_tokens=?,output_tokens=?,error=? WHERE id=?",
                        (now(), text, getattr(response, "input_tokens", None), getattr(response, "output_tokens", None), error, run_id))
                    await self.store.execute("UPDATE items SET state=?,updated_at=? WHERE id=?", (state, now(), item["id"]))
                await self.runtime.broadcast("item_changed", {"item_id": item["id"], "state": state})
                await self.check_all_triggered(item["plan_id"])
            else:
                current = await self.store.one("SELECT status FROM planning_runs WHERE id=?", (run_id,))
                if current and current["status"] not in {"completed", "failed"}:
                    next_status = "failed" if status == "error" else "no_change"
                    await self.store.execute("UPDATE planning_runs SET status=?,finished_at=? WHERE id=?", (next_status, now(), run_id))

    async def on_final(self, event) -> None:
        for metadata in ContextBuilder.metadata(event):
            if metadata["kind"] == "item":
                await self.store.execute("UPDATE runs SET status='finalized',finalized_at=? WHERE id=? AND responded_at IS NOT NULL", (now(), metadata["run_id"]))

    @staticmethod
    def is_silent(text: str) -> bool:
        compact = "".join(text.split())
        return not compact or compact in {"<msg/>", "<msg></msg>"}

    async def check_all_triggered(self, plan_id: str) -> None:
        plan = await self.plans.get_plan(plan_id)
        if not plan or not plan["persona_id"] or plan["persona_id"] != await self.runtime.active_persona_id():
            return
        config = await self.store.get_config(plan["persona_id"])
        if not config["plan_on_all_triggered"]:
            return
        active_states = "'scheduled','queued','running'" + ("" if config.get("all_terminal_include_failed") else ",'failed','interrupted'")
        counts = await self.store.one(
            f"SELECT COUNT(*) AS total,SUM(CASE WHEN state IN ({active_states}) THEN 1 ELSE 0 END) AS active,MAX(updated_at) AS latest FROM items WHERE plan_id=?",
            (plan_id,))
        if not counts or not counts["total"] or counts["active"]:
            return
        target = (datetime.fromisoformat(plan["date"]) + timedelta(days=1)).date().isoformat()
        trigger_id = f"all:{plan_id}:{int(counts['latest'])}"
        await self.trigger_planning(plan["persona_id"], "all_triggered", target, "All items reached a terminal state", trigger_id)

    async def run_now(self, persona_id: str, item_id: str) -> dict[str, Any]:
        item = await self.store.one("SELECT persona_id FROM items WHERE id=?", (item_id,))
        if not item or item["persona_id"] != persona_id:
            raise KRDError("not_found", "Item not found")
        run = await self.claim_item(item_id, manual=True)
        if not run:
            raise KRDError("cannot_run", "Item is not in a schedulable state")
        return run
