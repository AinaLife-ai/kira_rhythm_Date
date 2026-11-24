from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from .models import KRDError, new_id, now
from .store import Store
from .timeutils import timezone

THREAD_KINDS = ("goal", "promise", "project", "habit", "open_loop", "mystery")
THREAD_STATUSES = ("open", "paused", "done", "dropped", "deleted")
RESPONSE_VALUES = ("advance", "defer", "waiting", "no_change")
INTERNAL_RESPONSES = ("done", "dropped")
TERMINAL_STATUSES = {"done", "dropped", "deleted"}


def short_thread_id(identifier: str) -> str:
    value = str(identifier or "")
    return value.split("_", 1)[-1][:8] if value.startswith("thr_") else value[:8]


def _one_line(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


class ThreadService:
    """Long-lived goals and commitments, separate from plans and chat memory."""

    def __init__(self, store: Store, policy):
        self.store = store
        self.policy = policy

    # ------------------------------------------------------------------
    # Resolution and validation
    # ------------------------------------------------------------------
    async def resolve(self, persona_id: str, reference: str, *, include_deleted: bool = False) -> str:
        reference = str(reference or "").strip().lstrip("#")
        if not reference:
            raise KRDError("thread_required", "thread_id is required")
        suffix = "" if include_deleted else " AND status<>'deleted'"
        row = await self.store.one(
            f"SELECT id FROM threads WHERE persona_id=? AND id=?{suffix}",
            (persona_id, reference))
        if row:
            return row["id"]
        prefix = reference if reference.startswith("thr_") else f"thr_{reference}"
        candidates = await self.store.all(
            f"SELECT id FROM threads WHERE persona_id=?{suffix} AND id LIKE ?",
            (persona_id, f"{prefix}%"))
        if len(candidates) == 1:
            return candidates[0]["id"]
        if len(candidates) > 1:
            raise KRDError("ambiguous_thread", "Short thread id matches more than one thread")
        raise KRDError("thread_not_found", "Thread not found")

    async def resolve_link(self, persona_id: str, reference: str) -> str:
        identifier = await self.resolve(persona_id, reference)
        row = await self.store.one("SELECT status FROM threads WHERE id=?", (identifier,))
        if not row or row["status"] != "open":
            raise KRDError("thread_not_open", "Only an open thread can be linked to a plan item")
        return identifier

    @staticmethod
    def _parse_due(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, pattern)
                return parsed.strftime(pattern)
            except ValueError:
                continue
        raise KRDError("invalid_due_at", "due_at must be YYYY-MM-DD or YYYY-MM-DD HH:MM")

    @staticmethod
    def _limits(config: dict[str, Any]) -> dict[str, int]:
        threads = config.get("threads", {})
        return {
            "dossier_chars": int(threads.get("dossier_chars", 2000)),
            "next_step_chars": int(threads.get("next_step_chars", 200)),
            "log_chars": int(threads.get("log_chars", 500)),
            "planning_limit": int(threads.get("planning_limit", 8)),
            "full_dossier_in_planning": int(threads.get("full_dossier_in_planning", 5)),
            "excerpt_chars": int(threads.get("excerpt_chars", 300)),
            "logs_in_planning": int(threads.get("logs_in_planning", 3)),
            "chat_limit": int(threads.get("chat_limit", 5)),
            "execution_excerpt_chars": int(threads.get("execution_excerpt_chars", 300)),
            "execution_logs": int(threads.get("execution_logs", 2)),
        }

    def _timezone(self, config: dict[str, Any]) -> str:
        return self.policy.timezone_name(config)

    def _today(self, config: dict[str, Any]) -> date:
        return datetime.now(timezone(self._timezone(config))).date()

    def _due_info(self, due_at: str, config: dict[str, Any]) -> dict[str, Any]:
        if not due_at:
            return {}
        tz_name = self._timezone(config)
        try:
            if len(due_at) > 10:
                pattern = "%Y-%m-%d %H:%M:%S" if len(due_at) > 16 else "%Y-%m-%d %H:%M"
                value = datetime.strptime(due_at, pattern).replace(tzinfo=timezone(tz_name))
                seconds = (value.timestamp() - time.time())
                days = int(seconds // 86400)
                return {"due": due_at, "due_in_days": days,
                        "due_in_hours": int(seconds // 3600) if abs(seconds) < 86400 else None,
                        "overdue": seconds < 0}
            value = datetime.strptime(due_at, "%Y-%m-%d").date()
            days = (value - self._today(config)).days
            return {"due": due_at, "due_in_days": days, "overdue": days < 0}
        except ValueError:
            return {"due": due_at}

    def _public(self, row: dict[str, Any], config: dict[str, Any], *,
                dossier_mode: str = "none", excerpt_chars: int | None = None,
                log_limit: int = 0, log_chars: int | None = None) -> dict[str, Any]:
        limits = self._limits(config)
        dossier = str(row.get("dossier") or "")
        if dossier_mode == "excerpt":
            dossier = dossier[: excerpt_chars or limits["excerpt_chars"]]
            if len(str(row.get("dossier") or "")) > len(dossier):
                dossier += "…"
        elif dossier_mode == "none":
            dossier = ""
        result = {
            "id": row["id"],
            "short_id": short_thread_id(row["id"]),
            "kind": row.get("kind", "goal"),
            "title": row.get("title", ""),
            "status": row.get("status", "open"),
            "priority": int(row.get("priority", 1)),
            "next_step": row.get("next_step", ""),
            "due_at": str(row.get("due_at") or ""),
            "dossier": dossier,
            "last_touched": row.get("last_touched", 0),
            "created_at": row.get("created_at", 0),
            "updated_at": row.get("updated_at", 0),
            "source": row.get("source", "bot"),
            "stale_days": max(0, int((time.time() - float(row.get("last_touched") or 0)) // 86400)),
            "last_note": row.get("last_note", "") or "",
            "log_count": int(row.get("log_count", 0) or 0),
        }
        result.update(self._due_info(str(row.get("due_at") or ""), config))
        if log_limit:
            result["logs"] = [
                {"at": log["at"], "note": str(log["note"])[: (log_chars or limits["log_chars"])],
                 "item_id": log.get("item_id", ""), "kind": log.get("kind", "touch")}
                for log in row.get("logs", [])[:log_limit]
            ]
        return result

    async def _row(self, persona_id: str, identifier: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        where = "id=? AND persona_id=?"
        if not include_deleted:
            where += " AND status<>'deleted'"
        row = await self.store.one(f"SELECT * FROM threads WHERE {where}", (identifier, persona_id))
        if not row:
            return None
        latest = await self.store.one(
            "SELECT note FROM thread_logs WHERE thread_id=? ORDER BY at DESC LIMIT 1", (identifier,))
        count = await self.store.one(
            "SELECT COUNT(*) AS count FROM thread_logs WHERE thread_id=?", (identifier,))
        row["last_note"] = latest["note"] if latest else ""
        row["log_count"] = count["count"] if count else 0
        return row

    async def _logs(self, identifiers: Iterable[str], limit: int) -> dict[str, list[dict[str, Any]]]:
        ids = list(dict.fromkeys(identifiers))
        if not ids or limit <= 0:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = await self.store.all(
            f"SELECT thread_id,at,note,item_id,kind FROM thread_logs WHERE thread_id IN ({placeholders}) "
            "ORDER BY at DESC", tuple(ids))
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            bucket = result.setdefault(row["thread_id"], [])
            if len(bucket) < limit:
                bucket.append(row)
        return result

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    async def list(self, persona_id: str, *, status: str = "", kind: str = "",
                   limit: int = 50, include_deleted: bool = False) -> list[dict[str, Any]]:
        config = await self.store.get_config(persona_id)
        clauses = ["persona_id=?"]
        params: list[Any] = [persona_id]
        if status:
            if status not in THREAD_STATUSES:
                raise KRDError("invalid_thread_status", "Unknown thread status")
            clauses.append("status=?")
            params.append(status)
        elif not include_deleted:
            clauses.append("status<>'deleted'")
        if kind:
            if kind not in THREAD_KINDS:
                raise KRDError("invalid_thread_kind", "Unknown thread kind")
            clauses.append("kind=?")
            params.append(kind)
        limit = max(1, min(200, int(limit)))
        rows = await self.store.all(
            f"SELECT * FROM threads WHERE {' AND '.join(clauses)} "
            "ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'paused' THEN 1 WHEN 'done' THEN 2 ELSE 3 END,"
            "priority DESC, due_at='', due_at, last_touched DESC LIMIT ?",
            tuple(params + [limit]))
        logs = await self._logs([row["id"] for row in rows], 1)
        result = []
        for row in rows:
            row["last_note"] = (logs.get(row["id"]) or [{}])[0].get("note", "")
            row["log_count"] = 0
            result.append(self._public(row, config, dossier_mode="excerpt"))
        return result

    async def get(self, persona_id: str, reference: str) -> dict[str, Any] | None:
        identifier = await self.resolve(persona_id, reference, include_deleted=True)
        row = await self._row(persona_id, identifier, include_deleted=True)
        if row is None:
            return None
        config = await self.store.get_config(persona_id)
        logs = await self._logs([identifier], 200)
        row["logs"] = logs.get(identifier, [])
        return self._public(row, config, dossier_mode="full", log_limit=200)

    async def add(self, persona_id: str, payload: dict[str, Any], *, actor: str = "bot") -> dict[str, Any]:
        config = await self.store.get_config(persona_id)
        limits = self._limits(config)
        kind = str(payload.get("kind", "goal"))
        if kind not in THREAD_KINDS:
            raise KRDError("invalid_thread_kind", "Unknown thread kind")
        title = _one_line(payload.get("title", ""), 120)
        if not title:
            raise KRDError("thread_title_required", "Thread title is required")
        dossier = str(payload.get("dossier", "") or "")[: limits["dossier_chars"]]
        next_step = _one_line(payload.get("next_step", ""), limits["next_step_chars"])
        due_at = self._parse_due(payload.get("due_at", ""))
        try:
            priority = int(payload.get("priority", 1))
        except (TypeError, ValueError) as exc:
            raise KRDError("invalid_thread_priority", "Thread priority must be 0..3") from exc
        if not 0 <= priority <= 3:
            raise KRDError("invalid_thread_priority", "Thread priority must be 0..3")
        status = str(payload.get("status", "open"))
        if status not in {"open", "paused"}:
            raise KRDError("invalid_thread_status", "New threads must start open or paused")
        identifier = new_id("thr")
        timestamp = now()
        await self.store.execute(
            "INSERT INTO threads(id,persona_id,kind,title,dossier,status,priority,next_step,due_at,"
            "last_touched,created_at,updated_at,source,created_by,updated_by) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (identifier, persona_id, kind, title, dossier, status, priority, next_step, due_at,
             timestamp, timestamp, timestamp, str(payload.get("source", actor))[:40], actor, actor))
        row = await self._row(persona_id, identifier)
        return self._public(row or {}, config, dossier_mode="full")

    async def update(self, persona_id: str, reference: str, patch: dict[str, Any], *,
                     actor: str = "bot", note: str = "") -> dict[str, Any]:
        identifier = await self.resolve(persona_id, reference, include_deleted=True)
        config = await self.store.get_config(persona_id)
        limits = self._limits(config)
        row = await self._row(persona_id, identifier, include_deleted=True)
        if row is None:
            raise KRDError("thread_not_found", "Thread not found")
        changes: dict[str, Any] = {}
        for key, value in (patch or {}).items():
            if key in {"kind", "title", "dossier", "status", "priority", "next_step", "due_at"}:
                changes[key] = value
        if not changes:
            return self._public(row, config, dossier_mode="full")
        if "kind" in changes and changes["kind"] not in THREAD_KINDS:
            raise KRDError("invalid_thread_kind", "Unknown thread kind")
        if "title" in changes:
            changes["title"] = _one_line(changes["title"], 120)
            if not changes["title"]:
                raise KRDError("thread_title_required", "Thread title is required")
        if "dossier" in changes:
            changes["dossier"] = str(changes["dossier"] or "")[: limits["dossier_chars"]]
        if "next_step" in changes:
            changes["next_step"] = _one_line(changes["next_step"], limits["next_step_chars"])
        if "due_at" in changes:
            changes["due_at"] = self._parse_due(changes["due_at"])
        if "priority" in changes:
            try:
                changes["priority"] = int(changes["priority"])
            except (TypeError, ValueError) as exc:
                raise KRDError("invalid_thread_priority", "Thread priority must be 0..3") from exc
            if not 0 <= changes["priority"] <= 3:
                raise KRDError("invalid_thread_priority", "Thread priority must be 0..3")
        old_status = row.get("status", "open")
        if "status" in changes:
            status = str(changes["status"])
            if status not in THREAD_STATUSES:
                raise KRDError("invalid_thread_status", "Unknown thread status")
            changes["status"] = status
        changes["updated_at"] = now()
        changes["updated_by"] = actor
        assignments = ",".join(f"{key}=?" for key in changes)
        await self.store.execute(
            f"UPDATE threads SET {assignments} WHERE id=? AND persona_id=?",
            tuple(changes.values()) + (identifier, persona_id))
        new_status = str(changes.get("status", old_status))
        if new_status in TERMINAL_STATUSES and old_status not in TERMINAL_STATUSES:
            await self.store.execute(
                "INSERT INTO thread_logs(id,thread_id,persona_id,at,note,item_id,kind,actor) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (new_id("log"), identifier, persona_id, now(),
                 _one_line(note or f"标记为 {new_status}", limits["log_chars"]),
                 "", new_status, actor))
        row = await self._row(persona_id, identifier, include_deleted=True)
        result = self._public(row or {}, config, dossier_mode="full")
        result["changed"] = sorted(key for key in changes if key not in {"updated_at", "updated_by"})
        return result

    async def touch(self, persona_id: str, reference: str, note: str, *,
                    next_step: str | None = None, item_id: str = "", actor: str = "bot") -> dict[str, Any]:
        identifier = await self.resolve(persona_id, reference)
        config = await self.store.get_config(persona_id)
        limits = self._limits(config)
        text = _one_line(note, limits["log_chars"])
        if not text:
            raise KRDError("thread_note_required", "A short progress note is required")
        timestamp = now()
        fields = ["last_touched=?", "updated_at=?", "updated_by=?"]
        values: list[Any] = [timestamp, timestamp, actor]
        if next_step is not None:
            fields.insert(2, "next_step=?")
            values.insert(2, _one_line(next_step, limits["next_step_chars"]))
        await self.store.execute(
            f"UPDATE threads SET {','.join(fields)} WHERE id=? AND persona_id=? AND status<>'deleted'",
            tuple(values) + (identifier, persona_id))
        log_id = new_id("log")
        await self.store.execute(
            "INSERT INTO thread_logs(id,thread_id,persona_id,at,note,item_id,kind,actor) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (log_id, identifier, persona_id, timestamp, text, str(item_id or "")[:128], "touch", actor))
        row = await self._row(persona_id, identifier)
        result = self._public(row or {}, config, dossier_mode="excerpt")
        result["log"] = {"id": log_id, "at": timestamp, "note": text}
        return result

    async def close(self, persona_id: str, reference: str, status: str, note: str, *,
                    actor: str = "bot", run_id: str = "") -> dict[str, Any]:
        status = str(status or "")
        if status not in {"done", "dropped"}:
            raise KRDError("invalid_thread_status", "Closing status must be done or dropped")
        identifier = await self.resolve(persona_id, reference)
        config = await self.store.get_config(persona_id)
        limits = self._limits(config)
        text = _one_line(note, limits["log_chars"])
        if not text:
            raise KRDError("thread_note_required", "A closing note is required")
        timestamp = now()
        await self.store.execute(
            "UPDATE threads SET status=?,updated_at=?,updated_by=? WHERE id=? AND persona_id=?",
            (status, timestamp, actor, identifier, persona_id))
        await self.store.execute(
            "INSERT INTO thread_logs(id,thread_id,persona_id,at,note,item_id,kind,actor) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (new_id("log"), identifier, persona_id, timestamp, text, "", status, actor))
        if run_id:
            await self._record_one(run_id, persona_id, identifier, status, text)
        row = await self._row(persona_id, identifier)
        result = self._public(row or {}, config, dossier_mode="excerpt")
        result["closed"] = status
        return result

    async def delete(self, persona_id: str, reference: str, *, actor: str = "user") -> dict[str, Any]:
        identifier = await self.resolve(persona_id, reference)
        timestamp = now()
        await self.store.execute(
            "UPDATE threads SET status='deleted',updated_at=?,updated_by=? WHERE id=? AND persona_id=?",
            (timestamp, actor, identifier, persona_id))
        await self.store.execute(
            "INSERT INTO thread_logs(id,thread_id,persona_id,at,note,item_id,kind,actor) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (new_id("log"), identifier, persona_id, timestamp, "删除目标/约定", "", "deleted", actor))
        return {"id": identifier, "deleted": True}

    # ------------------------------------------------------------------
    # Planning responses
    # ------------------------------------------------------------------
    async def required(self, persona_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        config = await self.store.get_config(persona_id)
        limits = self._limits(config)
        limit = max(1, min(50, int(limit if limit is not None else limits["planning_limit"])))
        rows = await self.store.all(
            "SELECT * FROM threads WHERE persona_id=? AND status='open'", (persona_id,))
        if not rows:
            return []
        logs = await self._logs([row["id"] for row in rows], limits["logs_in_planning"])
        for row in rows:
            row["logs"] = logs.get(row["id"], [])
            row["last_note"] = (row["logs"] or [{}])[0].get("note", "")
            row["log_count"] = len(row["logs"])
        def sort_key(row: dict[str, Any]) -> tuple:
            info = self._due_info(str(row.get("due_at") or ""), config)
            due_days = info.get("due_in_days", 10**6)
            return (due_days, -int(row.get("priority", 1)),
                    -max(0, int((time.time() - float(row.get("last_touched") or 0)) // 86400)),
                    float(row.get("last_touched") or 0))

        rows.sort(key=sort_key)
        result = []
        for index, row in enumerate(rows[:limit]):
            padded = self._public(
                row, config, dossier_mode="full" if index < limits["full_dossier_in_planning"] else "excerpt",
                excerpt_chars=limits["excerpt_chars"], log_limit=limits["logs_in_planning"],
                log_chars=limits["log_chars"])
            padded["response_required"] = True
            result.append(padded)
        return result

    async def planning_payload(self, persona_id: str) -> dict[str, Any]:
        config = await self.store.get_config(persona_id)
        if not config.get("threads", {}).get("enabled", True):
            return {"required": False, "threads": [], "more": 0, "contract": ""}
        required = await self.required(persona_id)
        if not required:
            return {"required": False, "threads": [], "more": 0, "contract": ""}
        total = await self.store.one(
            "SELECT COUNT(*) AS count FROM threads WHERE persona_id=? AND status='open'", (persona_id,))
        more = max(0, int(total["count"] if total else 0) - len(required))
        contract = (
            "本次规划必须先调用 rhythm_update 的 thread_response，逐条回应下列 id；"
            "advance / defer / waiting / no_change + 一句原因。回应不等于必须推进，no_change 合法；"
            "no_change 也必须写一句依据。未覆盖会返回 thread_response_missing。")
        return {"required": True, "threads": required, "more": more, "contract": contract}

    async def _record_one(self, run_id: str, persona_id: str, thread_id: str,
                          response: str, note: str) -> None:
        if response not in RESPONSE_VALUES + INTERNAL_RESPONSES:
            raise KRDError("invalid_thread_response", "Unknown thread response")
        text = _one_line(note, 1000)
        if not text:
            raise KRDError("thread_response_note_required", "Each response requires a short reason")
        timestamp = now()
        await self.store.execute(
            "INSERT INTO thread_responses(id,run_id,persona_id,thread_id,response,note,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(run_id,thread_id) DO UPDATE SET "
            "response=excluded.response,note=excluded.note,updated_at=excluded.updated_at",
            (new_id("trs"), run_id, persona_id, thread_id, response, text, timestamp, timestamp))

    async def record_responses(self, persona_id: str, run_id: str, responses: list[dict[str, Any]],
                               *, actor: str = "bot") -> dict[str, Any]:
        if not run_id:
            raise KRDError("thread_response_outside_planning",
                           "thread_response is only available during a planning run")
        run = await self.store.one("SELECT * FROM planning_runs WHERE id=? AND persona_id=?", (run_id, persona_id))
        if not run:
            raise KRDError("planning_run_not_found", "Planning run not found")
        if run.get("kind") == "review":
            raise KRDError("thread_response_outside_planning",
                           "thread_response is only for a full planning run, not a review")
        required_ids = set(json.loads(run.get("required_thread_ids_json") or "[]"))
        config = await self.store.get_config(persona_id)
        limits = self._limits(config)
        recorded = []
        for entry in responses:
            if not isinstance(entry, dict):
                raise KRDError("invalid_thread_response", "Each thread response must be an object")
            reference = str(entry.get("thread_id", ""))
            identifier = await self.resolve(persona_id, reference)
            response = str(entry.get("response", ""))
            if response not in RESPONSE_VALUES:
                raise KRDError("invalid_thread_response", "Response must be advance/defer/waiting/no_change")
            note = _one_line(entry.get("note", ""), limits["log_chars"])
            if not note:
                raise KRDError("thread_response_note_required", "Each response requires a short reason")
            row = await self.store.one("SELECT status FROM threads WHERE id=?", (identifier,))
            if not row or row["status"] != "open":
                raise KRDError("thread_not_open", "Only open threads can be answered")
            await self._record_one(run_id, persona_id, identifier, response, note)
            recorded.append({"thread_id": identifier, "short_id": short_thread_id(identifier),
                             "response": response, "note": note})
        missing = await self.missing_for_run(run_id)
        status = "done" if not missing else "partial"
        await self.store.execute(
            "UPDATE planning_runs SET response_status=? WHERE id=?", (status, run_id))
        return {"recorded": recorded, "missing": missing, "status": status,
                "required": sorted(required_ids)}

    async def missing_for_run(self, run_id: str) -> list[dict[str, Any]]:
        run = await self.store.one("SELECT * FROM planning_runs WHERE id=?", (run_id,))
        if not run:
            return []
        required_ids = json.loads(run.get("required_thread_ids_json") or "[]")
        if not required_ids:
            return []
        placeholders = ",".join("?" for _ in required_ids)
        threads = await self.store.all(
            f"SELECT id,title,status FROM threads WHERE id IN ({placeholders})", tuple(required_ids))
        responded = await self.store.all(
            "SELECT thread_id FROM thread_responses WHERE run_id=?", (run_id,))
        answered = {row["thread_id"] for row in responded}
        missing = []
        for row in threads:
            if row["status"] != "open":
                continue
            if row["id"] not in answered:
                missing.append({"id": row["id"], "short_id": short_thread_id(row["id"]), "title": row["title"]})
        return missing

    async def finalize_run(self, run_id: str) -> str:
        run = await self.store.one("SELECT * FROM planning_runs WHERE id=?", (run_id,))
        if not run:
            return ""
        if not run.get("required_thread_ids_json") or json.loads(run["required_thread_ids_json"] or "[]") == []:
            status = "not_required"
        else:
            missing = await self.missing_for_run(run_id)
            status = "missing" if missing else "done"
        await self.store.execute("UPDATE planning_runs SET response_status=? WHERE id=?", (status, run_id))
        return status

    async def unanswered(self, persona_id: str) -> list[dict[str, Any]]:
        run = await self.store.one(
            "SELECT * FROM planning_runs WHERE persona_id=? AND kind<>'review' "
            "AND response_status IN ('missing','partial') ORDER BY created_at DESC LIMIT 1", (persona_id,))
        if not run:
            return []
        return await self.missing_for_run(run["id"])

    # ------------------------------------------------------------------
    # Context surfaces
    # ------------------------------------------------------------------
    async def chat_block(self, persona_id: str, config: dict[str, Any] | None = None) -> str:
        config = config or await self.store.get_config(persona_id)
        settings = config.get("threads", {})
        if not settings.get("enabled", True) or not settings.get("chat_enabled", True):
            return ""
        limit = max(1, min(8, int(settings.get("chat_limit", 5))))
        rows = await self.store.all(
            "SELECT * FROM threads WHERE persona_id=? AND status IN ('open','paused') "
            "ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, priority DESC, due_at='', due_at, last_touched ASC LIMIT ?",
            (persona_id, limit))
        if not rows:
            return ""
        total = await self.store.one(
            "SELECT COUNT(*) AS count FROM threads WHERE persona_id=? AND status IN ('open','paused')", (persona_id,))
        more = max(0, int(total["count"] if total else 0) - len(rows))
        stale_limit = int(settings.get("stale_days", 5))
        item_lines = []
        for row in rows:
            info = self._due_info(str(row.get("due_at") or ""), config)
            stale = max(0, int((time.time() - float(row.get("last_touched") or 0)) // 86400))
            marker = "[~]" if row["status"] == "paused" else "[!]" if (
                info.get("overdue") or info.get("due_in_days", 999) <= 1 or stale >= stale_limit) else "[ ]"
            line = f"{marker} {_one_line(row['title'], 80)}  {row['kind']}"
            if info.get("due"):
                due = info["due"]
                days = info.get("due_in_days")
                if info.get("overdue"):
                    line += f"  due {due[5:]} ({abs(days)}d overdue)" if days is not None else f"  due {due[5:]}"
                elif days == 0:
                    line += f"  due {due[5:]} (today)"
                else:
                    line += f"  due {due[5:]} ({days}d)"
            elif stale:
                line += f"  idle {stale}d"
            line += f"  #{short_thread_id(row['id'])}  next: {_one_line(row.get('next_step'), 80) or '—'}"
            item_lines.append(line)
        max_chars = max(100, int(settings.get("chat_chars", 600)))
        while item_lines and len("\n".join(["[KRD Threads]", *item_lines, *([f"(+{more} more)"] if more else [])])) > max_chars:
            item_lines.pop()
            more += 1
        lines = ["[KRD Threads]", *item_lines]
        if more:
            lines.append(f"(+{more} more)")
        return "\n".join(lines)

    async def execution_payload(self, persona_id: str, thread_id: str,
                                config: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not thread_id:
            return None
        config = config or await self.store.get_config(persona_id)
        limits = self._limits(config)
        try:
            identifier = await self.resolve(persona_id, thread_id)
        except KRDError:
            return None
        row = await self._row(persona_id, identifier)
        if row is None:
            return None
        logs = await self._logs([identifier], limits["execution_logs"])
        row["logs"] = logs.get(identifier, [])
        return self._public(row, config, dossier_mode="excerpt",
                            excerpt_chars=limits["execution_excerpt_chars"],
                            log_limit=limits["execution_logs"], log_chars=limits["log_chars"])

    async def review_payload(self, persona_id: str, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        config = config or await self.store.get_config(persona_id)
        rows = await self.store.all(
            "SELECT * FROM threads WHERE persona_id=? AND status='open' "
            "ORDER BY priority DESC, due_at='', due_at, last_touched ASC LIMIT 5", (persona_id,))
        logs = await self._logs([row["id"] for row in rows], 1)
        result = []
        for row in rows:
            row["logs"] = logs.get(row["id"], [])
            row["last_note"] = (row["logs"] or [{}])[0].get("note", "")
            item = self._public(row, config, dossier_mode="none")
            item["last_note"] = _one_line(item.get("last_note"), 120)
            result.append(item)
        return result

    async def auto_touch(self, persona_id: str, thread_id: str, note: str, *, item_id: str = "") -> None:
        try:
            await self.touch(persona_id, thread_id, note, item_id=item_id, actor="bot")
        except Exception:
            return

    async def item_was_touched(self, thread_id: str, item_id: str, since: float) -> bool:
        if not thread_id or not item_id:
            return False
        row = await self.store.one(
            "SELECT 1 AS used FROM thread_logs WHERE thread_id=? AND item_id=? AND at>=? LIMIT 1",
            (thread_id, item_id, float(since or 0)))
        return bool(row)

    async def untouched(self, persona_id: str, days: int = 3) -> list[dict[str, Any]]:
        config = await self.store.get_config(persona_id)
        today = self._today(config)
        start = (today - timedelta(days=max(1, days))).isoformat()
        rows = await self.store.all(
            "SELECT p.date AS date,i.title AS title,t.title AS thread_title FROM runs r "
            "JOIN items i ON i.id=r.item_id JOIN plans p ON p.id=i.plan_id "
            "LEFT JOIN threads t ON t.id=i.thread_id "
            "WHERE p.persona_id=? AND p.date>=? AND r.error LIKE '%thread_untouched%' "
            "ORDER BY r.responded_at DESC LIMIT 5", (persona_id, start))
        return [{"date": row["date"], "title": row["title"], "thread": row.get("thread_title", "")}
                for row in rows]

    async def counts(self, persona_id: str) -> dict[str, int]:
        rows = await self.store.all(
            "SELECT status,COUNT(*) AS count FROM threads WHERE persona_id=? GROUP BY status", (persona_id,))
        return {row["status"]: int(row["count"]) for row in rows}
