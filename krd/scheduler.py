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
from .store import Store, dumps
from .timeutils import in_active_windows, next_daily, timezone, to_utc


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
        self.last_cleanup = 0.0
        self.watchdog_seconds = 900.0
        self._watchdogs: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        await self.recover()
        await self._startup_planning()
        self.task = asyncio.create_task(self._loop(), name="krd_scheduler")

    async def _startup_planning(self) -> None:
        persona_id = await self.runtime.active_persona_id()
        if not persona_id:
            return
        config = await self.store.get_config(persona_id)
        if not config["enabled"] or not config["auto_plan"] or not config["startup_plan"]:
            return
        today = await self.plans.current_date(persona_id)
        tomorrow = (datetime.fromisoformat(today) + timedelta(days=1)).date().isoformat()
        if not await self.plans.get_plan_by_date(persona_id, today):
            target = today
        elif not await self.plans.get_plan_by_date(persona_id, tomorrow):
            target = tomorrow
        else:
            return
        await self.trigger_planning(persona_id, "startup", target, "Startup found a missing current/next-day plan")

    async def stop(self) -> None:
        self.running = False
        self.wake_event.set()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        watchdogs = list(self._watchdogs.values())
        self._watchdogs.clear()
        for task in watchdogs:
            task.cancel()
        if watchdogs:
            await asyncio.gather(*watchdogs, return_exceptions=True)

    def wake(self) -> None:
        self.wake_event.set()

    async def recover(self) -> None:
        timestamp = now()
        async with self.store.transaction() as db:
            await db.execute(
                "UPDATE runs SET status='interrupted',finalized_at=?,error='Interrupted before confirmed response' "
                "WHERE status IN ('prepared','queued','running')", (timestamp,))
            await db.execute(
                "UPDATE items SET state='interrupted',updated_at=? WHERE state IN ('queued','running') "
                "AND EXISTS(SELECT 1 FROM runs r WHERE r.item_id=items.id AND r.status='interrupted' AND r.finalized_at=?)",
                (timestamp, timestamp))

    async def _loop(self) -> None:
        while self.running:
            try:
                await self.dispatch_due()
                await self._maybe_cleanup()
                due = await self.next_due()
                # The cap also detects active-persona changes made outside KRD;
                # ordinary schedule/config changes wake us immediately instead.
                timeout = 30 if due is None else max(0.05, min(due - time.time(), 30))
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

    async def _maybe_cleanup(self) -> None:
        monotonic = time.monotonic()
        if monotonic - self.last_cleanup < 21600:
            return
        persona_id = await self.runtime.active_persona_id()
        if persona_id:
            config = await self.store.get_config(persona_id)
            await self.store.cleanup(persona_id, config["retention_days"], await self.plans.current_date(persona_id))
        self.last_cleanup = monotonic

    async def _review_candidate(self, persona_id: str, config: dict[str, Any]) -> dict[str, Any] | None:
        review = config["planning_review"]
        if not review["enabled"]:
            return None
        timestamp = time.time()
        row = await self.store.one(
            "SELECT i.id,i.plan_id,i.scheduled_at,i.target,p.date,p.updated_at FROM items i JOIN plans p ON p.id=i.plan_id "
            "WHERE p.persona_id=? AND p.state='active' AND i.state='scheduled' AND i.scheduled_at>? "
            "ORDER BY i.scheduled_at LIMIT 1", (persona_id, timestamp))
        lead_seconds = review.get("min_lead_seconds")
        if type(lead_seconds) is not int:
            lead_seconds = review["min_lead_minutes"] * 60
        if not row or row["scheduled_at"] - timestamp < lead_seconds:
            return None
        last = await self.store.one(
            "SELECT MAX(created_at) AS latest FROM planning_runs WHERE persona_id=? AND kind='review' AND target_date=?",
            (persona_id, row["date"]))
        base = max(float(row["updated_at"]), float(last["latest"] or 0))
        interval_seconds = review.get("interval_seconds")
        if type(interval_seconds) is not int:
            interval_seconds = review["interval_minutes"] * 60
        scheduled_due = base + interval_seconds
        if scheduled_due >= row["scheduled_at"]:
            return None
        due = scheduled_due
        if due <= timestamp:
            tz_name = self.policy.timezone_name(config)
            unavailable = in_active_windows(
                [*config["blocked_execution_windows"], *config["quiet_delivery_windows"]], timestamp, tz_name)
            if unavailable:
                due = timestamp + 300
        return {"due": due, "scheduled_due": scheduled_due, **row}

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
        review = await self._review_candidate(persona_id, config)
        if review:
            candidates.append(float(review["due"]))
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
        review = await self._review_candidate(persona_id, config)
        if review and review["due"] <= time.time():
            trigger_id = f"review:{review['plan_id']}:{review['id']}:{int(review['scheduled_due'])}"
            await self.trigger_planning(
                persona_id, "review", review["date"], "Review whether the current plan still fits",
                trigger_id, session_id=review["target"])

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
        run = None
        terminal = False
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
                state = "missed"
                terminal = True
                await db.execute("UPDATE items SET state='missed',updated_at=? WHERE id=? AND state='scheduled'", (timestamp, item_id))
            else:
                probability = 1.0 if manual else float(item["execution_probability"])
                draw = self.rng.random()
                skipped = draw >= probability
                state = "skipped_probability" if skipped else "queued"
                terminal = skipped
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
        if run and run["status"] == "prepared":
            if not await self.publish_run(run):
                run["status"] = "failed"
                state = "failed"
                terminal = True
        await self.runtime.broadcast("item_changed", {"item_id": item_id, "state": state})
        if not manual and terminal:
            await self.check_all_triggered(item["plan_id"])
        return run

    async def trigger_planning(self, persona_id: str, kind: str, target_date: str, reason: str,
                               trigger_id: str | None = None, session_id: str = "") -> dict[str, Any] | None:
        if not persona_id:
            return None
        if persona_id != await self.runtime.active_persona_id():
            if kind == "manual":
                raise KRDError("persona_not_active", "Planning can only run for the active persona")
            return None
        config = await self.store.get_config(persona_id)
        if not config["enabled"] or (kind not in {"manual", "review"} and not config["auto_plan"]):
            if kind == "manual":
                raise KRDError("planning_disabled", "Enable this persona's life rhythm before planning")
            return None
        trigger_id = trigger_id or new_id(f"trg_{kind}")
        existing = await self.store.one("SELECT * FROM planning_runs WHERE trigger_id=?", (trigger_id,))
        if existing:
            return existing
        try:
            if session_id:
                if not await self.policy.is_allowed(persona_id, session_id, "execution", config=config):
                    raise KRDError("session_denied", "Review target is not allowed by execution permissions")
                target = session_id
            else:
                target = await self.policy.require_target(persona_id, "", "planning")
        except KRDError as exc:
            if kind == "manual":
                raise
            # Record automatic dispatch failure so a missing adapter/session does
            # not make the scheduler retry and log every five seconds forever.
            run = {"id": new_id("prn"), "trigger_id": trigger_id, "persona_id": persona_id, "kind": kind,
                   "target_date": target_date, "session_id": "", "status": "failed", "reason": reason}
            await self.store.execute(
                "INSERT OR IGNORE INTO planning_runs(id,trigger_id,persona_id,kind,target_date,session_id,status,reason,created_at,finished_at,error) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (run["id"], trigger_id, persona_id, kind, target_date, "", "failed", reason, now(), now(), exc.message))
            return await self.store.one("SELECT * FROM planning_runs WHERE trigger_id=?", (trigger_id,))
        required_ids: list[str] = []
        threads_service = getattr(self.runtime, "threads", None)
        if kind != "review" and config.get("threads", {}).get("enabled", True) and \
                config.get("threads", {}).get("require_response", True) and threads_service is not None:
            try:
                required = await threads_service.required(
                    persona_id, config.get("threads", {}).get("response_limit", 8))
                required_ids = [row["id"] for row in required]
            except Exception as exc:
                self.runtime.log("warning", "thread_required_failed", error=repr(exc))
        # Keep the planning room clean before this run is recorded, so the summary
        # describes the previous planning turn rather than the empty current one.
        hygiene = getattr(self.runtime, "hygiene", None)
        if hygiene is not None:
            await hygiene.prepare(target, persona_id)
        run = {"id": new_id("prn"), "trigger_id": trigger_id, "persona_id": persona_id, "kind": kind,
               "target_date": target_date, "session_id": target, "status": "prepared", "reason": reason,
               "required_thread_ids_json": dumps(required_ids),
               "response_status": "pending" if required_ids else "not_required"}
        async with self.store.transaction() as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO planning_runs(id,trigger_id,persona_id,kind,target_date,session_id,status,"
                "required_thread_ids_json,response_status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (run["id"], trigger_id, persona_id, kind, target_date, target, "prepared",
                 run["required_thread_ids_json"], run["response_status"], reason, now()))
            if cursor.rowcount != 1:
                return await self.store.one("SELECT * FROM planning_runs WHERE trigger_id=?", (trigger_id,))
        if not await self.publish_run(run):
            run["status"] = "failed"
            if kind == "manual":
                raise KRDError("dispatch_failed", "Planning event could not be dispatched; inspect adapter permissions")
        return run

    async def publish_run(self, run: dict[str, Any]) -> bool:
        # run.kind stores the trigger reason; prompt metadata exposes the
        # distinct item/planning/review contracts.
        kind = "item" if run["kind"] == "item" else "review" if run["kind"] == "review" else "planning"
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
                metadata.update({"item_id": "", "plan_id": "", "date": run["target_date"],
                                 "trigger_id": run["trigger_id"], "reason": run.get("reason", "")})
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
            self._arm_watchdog(run_id, kind)
            await self.runtime.broadcast("run_queued", {"run_id": run_id, "kind": kind})
            return True
        except Exception as exc:
            if kind == "item":
                await self.store.execute("UPDATE runs SET status='failed',error=? WHERE id=?", (str(exc), run_id))
                await self.store.execute("UPDATE items SET state='failed',updated_at=? WHERE id=?", (now(), run["item_id"]))
            else:
                await self.store.execute("UPDATE planning_runs SET status='failed',error=?,finished_at=? WHERE id=?", (str(exc), now(), run_id))
            self.runtime.log("warning", "dispatch_failed", run_id=run_id, error=str(exc))
            await self.runtime.broadcast("run_failed", {"run_id": run_id, "kind": kind, "error": str(exc)})
            return False

    def _arm_watchdog(self, run_id: str, kind: str) -> None:
        self._clear_watchdog(run_id)
        task = asyncio.create_task(self._watchdog(run_id, kind), name=f"krd_watchdog:{run_id}")
        self._watchdogs[run_id] = task

        def finished(completed: asyncio.Task) -> None:
            if self._watchdogs.get(run_id) is completed:
                self._watchdogs.pop(run_id, None)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)

    def _clear_watchdog(self, run_id: str) -> None:
        task = self._watchdogs.pop(run_id, None)
        if task and not task.done():
            task.cancel()

    async def _watchdog(self, run_id: str, kind: str) -> None:
        await asyncio.sleep(self.watchdog_seconds)
        changed = False
        async with self.store.transaction() as db:
            if kind == "item":
                run = await self.store.one("SELECT item_id,status FROM runs WHERE id=?", (run_id,))
                if run and run["status"] in {"prepared", "queued", "running"}:
                    await db.execute(
                        "UPDATE runs SET status='interrupted',finalized_at=?,error='Workflow watchdog timeout' WHERE id=?",
                        (now(), run_id))
                    await db.execute(
                        "UPDATE items SET state='interrupted',updated_at=? WHERE id=? AND state IN ('queued','running')",
                        (now(), run["item_id"]))
                    changed = True
            else:
                cursor = await db.execute(
                    "UPDATE planning_runs SET status='interrupted',finished_at=?,error='Workflow watchdog timeout' "
                    "WHERE id=? AND status IN ('prepared','queued','running')", (now(), run_id))
                changed = cursor.rowcount == 1
        if changed:
            await self.runtime.broadcast("run_interrupted", {"run_id": run_id, "kind": kind})

    async def on_request(self, event) -> None:
        active = await self.runtime.active_persona_id()
        allowed_runs = getattr(event, "_krd_allowed_run_ids", None)
        for metadata in ContextBuilder.metadata(event):
            if metadata.get("persona_id") != active:
                continue
            if allowed_runs is not None and metadata["run_id"] not in allowed_runs:
                continue
            if metadata["kind"] == "item":
                await self.store.execute("UPDATE runs SET status='running' WHERE id=? AND status IN ('prepared','queued')", (metadata["run_id"],))
            else:
                await self.store.execute("UPDATE planning_runs SET status='running' WHERE id=? AND status IN ('prepared','queued')", (metadata["run_id"],))

    @staticmethod
    def has_real_user(event) -> bool:
        return any(
            not (getattr(message, "extra", None) or {}).get("krd") and not getattr(message, "is_notice", False)
            for message in getattr(event, "messages", []) or [])

    async def _thread_active(self, thread_id: str) -> bool:
        if not thread_id:
            return False
        row = await self.store.one("SELECT status FROM threads WHERE id=?", (thread_id,))
        return bool(row and row.get("status") in {"open", "paused"})

    async def on_response(self, event, response) -> None:
        text = str(getattr(response, "text_response", "") or "")
        has_tool_calls = bool(getattr(response, "tool_calls", None))
        text_silent = self.is_silent(text)
        silent = text_silent and not has_tool_calls
        status = getattr(response, "status", "success")
        active_persona = await self.runtime.active_persona_id()
        for metadata in ContextBuilder.metadata(event):
            if metadata["persona_id"] != active_persona:
                continue
            run_id = metadata["run_id"]
            self._clear_watchdog(run_id)
            if metadata["kind"] == "item":
                run = await self.store.one("SELECT * FROM runs WHERE id=?", (run_id,))
                if not run:
                    continue
                item = await self.store.one("SELECT * FROM items WHERE id=?", (run["item_id"],))
                if not item:
                    continue
                if status == "error":
                    await self.store.execute("UPDATE runs SET status='failed',responded_at=?,raw_output=?,error=? WHERE id=?",
                                             (now(), text[:20000], "model_error", run_id))
                    await self.store.execute("UPDATE items SET state='failed',updated_at=? WHERE id=?", (now(), item["id"]))
                    state = "failed"
                else:
                    config = await self.store.get_config(run["persona_id"])
                    effective = config
                    plan_row = await self.store.one(
                        "SELECT date,day_type_id FROM plans WHERE id=?", (item["plan_id"],))
                    if plan_row:
                        try:
                            effective = await self.plans.effective_config(
                                run["persona_id"], plan_row.get("day_type_id", ""))
                        except Exception:
                            effective = config
                    quiet_now = in_active_windows(
                        effective["quiet_delivery_windows"], time.time(), self.policy.timezone_name(effective))
                    # In a mixed batch a visible answer to the real user is
                    # mandatory; the item's silence only constrains its own
                    # share of the reply.
                    silence_requested = (item["interaction"] == "silent" or
                                         (quiet_now and item["interaction"] == "auto")) and not self.has_real_user(event)
                    # Never rewrite model output. Record what actually happened and
                    # expose prompt non-compliance as diagnostics instead of hiding it.
                    state = "triggered_silent" if silent else "triggered"
                    if silence_requested and not text_silent:
                        error = "silence_unmet"
                    elif item["interaction"] == "must_message" and text_silent:
                        error = "delivery_unmet"
                    else:
                        error = ""
                    await self.store.execute(
                        "UPDATE runs SET status='responded',responded_at=?,raw_output=?,input_tokens=?,output_tokens=?,error=? WHERE id=?",
                        (now(), text[:20000], getattr(response, "input_tokens", None), getattr(response, "output_tokens", None), error, run_id))
                    await self.store.execute("UPDATE items SET state=?,updated_at=? WHERE id=?", (state, now(), item["id"]))
                    threads_service = getattr(self.runtime, "threads", None)
                    if threads_service is not None and item.get("thread_id") and config.get("threads", {}).get("enabled", True):
                        settings = config.get("threads", {})
                        if settings.get("auto_touch", False) and await self._thread_active(item["thread_id"]):
                            already = await threads_service.item_was_touched(
                                item["thread_id"], item["id"], float(run.get("claimed_at") or 0))
                            if not already:
                                await threads_service.auto_touch(
                                    run["persona_id"], item["thread_id"],
                                    f"执行了「{item['title']}」", item_id=item["id"])

                await self.runtime.broadcast("item_changed", {"item_id": item["id"], "state": state})
                if run["status"] not in {"responded", "finalized", "failed"}:
                    await self.check_all_triggered(item["plan_id"])
            else:
                current = await self.store.one("SELECT status FROM planning_runs WHERE id=?", (run_id,))
                if current and current["status"] not in {"completed", "failed"}:
                    next_status = "failed" if status == "error" else "no_change"
                    await self.store.execute("UPDATE planning_runs SET status=?,finished_at=? WHERE id=?", (next_status, now(), run_id))
                threads_service = getattr(self.runtime, "threads", None)
                if threads_service is not None:
                    try:
                        await threads_service.finalize_run(run_id)
                    except Exception as exc:
                        self.runtime.log("warning", "thread_response_finalize_failed", error=repr(exc))

    async def on_final(self, event) -> None:
        active = await self.runtime.active_persona_id()
        for metadata in ContextBuilder.metadata(event):
            if metadata.get("persona_id") != active:
                continue
            if metadata["kind"] != "item":
                continue
            run_id = metadata["run_id"]
            run = await self.store.one("SELECT * FROM runs WHERE id=?", (run_id,))
            item = await self.store.one("SELECT * FROM items WHERE id=?", (run["item_id"],)) if run else None
            if run and item and item.get("thread_id") and run.get("status") in {"responded", "finalized"}:
                config = await self.store.get_config(run["persona_id"])
                settings = config.get("threads", {})
                threads_service = getattr(self.runtime, "threads", None)
                if (threads_service is not None and settings.get("enabled", True)
                        and settings.get("force_touch", False)
                        and await self._thread_active(item["thread_id"])):
                    touched = await threads_service.item_was_touched(
                        item["thread_id"], item["id"], float(run.get("claimed_at") or 0))
                    if not touched:
                        await self.store.execute(
                            "UPDATE runs SET error=CASE WHEN error='' THEN 'thread_untouched' "
                            "WHEN error LIKE '%thread_untouched%' THEN error ELSE error || ',thread_untouched' END "
                            "WHERE id=?", (run_id,))
            await self.store.execute(
                "UPDATE runs SET status='finalized',finalized_at=? WHERE id=? AND responded_at IS NOT NULL",
                (now(), run_id))

    @staticmethod
    def is_silent(text: str) -> bool:
        compact = "".join(text.split())
        return not compact or compact in {"<msg/>", "<msg></msg>"}

    async def check_all_triggered(self, plan_id: str) -> None:
        plan = await self.store.one("SELECT id,persona_id,date FROM plans WHERE id=?", (plan_id,))
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
        session_id = ""
        if config["all_triggered_target_mode"] == "last_session":
            latest = await self.store.one(
                "SELECT session_id FROM runs WHERE plan_id=? AND responded_at IS NOT NULL "
                "ORDER BY responded_at DESC,claimed_at DESC,id DESC LIMIT 1", (plan_id,))
            if latest and await self.policy.is_allowed(
                    plan["persona_id"], latest["session_id"], "execution", config=config):
                session_id = latest["session_id"]
        await self.trigger_planning(
            plan["persona_id"], "all_triggered", target, "All items reached a terminal state", trigger_id,
            session_id=session_id)

    async def run_now(self, persona_id: str, item_id: str) -> dict[str, Any]:
        if persona_id != await self.runtime.active_persona_id():
            raise KRDError("persona_not_active", "Items can only run for the active persona")
        item = await self.store.one(
            "SELECT p.persona_id FROM items i JOIN plans p ON p.id=i.plan_id WHERE i.id=?", (item_id,))
        if not item or item["persona_id"] != persona_id:
            raise KRDError("not_found", "Item not found")
        run = await self.claim_item(item_id, manual=True)
        if not run:
            raise KRDError("cannot_run", "Item is not in a schedulable state")
        if run["status"] == "failed":
            raise KRDError("dispatch_failed", "Item event could not be dispatched; inspect adapter permissions")
        return run
