from __future__ import annotations

import json
from fastapi import File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from core.plugin import PageMenu, PluginPage, register

from . import webapi
from .models import KRDError, new_id, now


class ApiMixin:
    async def _call(self, function, *args, **kwargs):
        try:
            return await function(*args, **kwargs)
        except KRDError as exc:
            status = 409 if "conflict" in exc.code or exc.code == "modify_budget" else 400
            raise HTTPException(status_code=status, detail=exc.as_dict()) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"code": type(exc).__name__, "message": str(exc)}) from exc

    async def _persona(self, persona: str = "") -> str:
        if self.runtime is None:
            raise KRDError("runtime_unavailable", "KRD is not initialized")
        return await self.runtime.active_persona_id() if not persona else persona

    @register.page("/dashboard", menu=PageMenu(label={"zh": "生活节律", "en": "Rhythm"}, icon="Calendar", order=70))
    def krd_page(self):
        return PluginPage.from_folder("./web")

    @register.static("/assets", "assets")
    def krd_static(self):
        return None

    @register.api(method="GET", path="/v1/bootstrap")
    async def api_bootstrap(self, persona: str = ""):
        return await self._call(lambda: webapi.bootstrap(self.runtime, persona))

    @register.api(method="GET", path="/v1/plans")
    async def api_plans(self, start: str, end: str, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.plans.list_plans, persona_id, start, end)

    @register.api(method="GET", path="/v1/plans/{plan_id}")
    async def api_plan(self, plan_id: str, persona: str = ""):
        persona_id = await self._persona(persona)
        async def load():
            plan = await self.runtime.plans.get_plan(plan_id, persona_id)
            if not plan:
                raise KRDError("not_found", "Plan not found")
            return plan
        return await self._call(load)

    @register.api(method="POST", path="/v1/plans")
    async def api_save_plan(self, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.plans.apply_plan, persona_id, payload, actor="user",
                                mode=payload.get("mode", "revise"), reason=payload.get("reason", "WebUI edit"),
                                expected_revision=int(payload.get("expected_revision", 0)))

    @register.api(method="GET", path="/v1/plans/{plan_id}/diff")
    async def api_diff(self, plan_id: str, limit: int = 10):
        return await self._call(self.runtime.plans.revisions, plan_id, limit)

    @register.api(method="POST", path="/v1/planning/run")
    async def api_run_planning(self, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        day = payload.get("date") or await self.runtime.plans.current_date(persona_id)
        return await self._call(self.runtime.scheduler.trigger_planning, persona_id, "manual", day,
                                payload.get("reason", "Manual planning from WebUI"))

    @register.api(method="PATCH", path="/v1/items/{item_id}")
    async def api_update_item(self, item_id: str, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.plans.update_item, persona_id, item_id, payload,
                                actor="user", reason=payload.get("reason", "WebUI edit"))

    @register.api(method="POST", path="/v1/items/{item_id}/run")
    async def api_run_item(self, item_id: str, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.scheduler.run_now, persona_id, item_id)

    @register.api(method="POST", path="/v1/items/{item_id}/skip")
    async def api_skip_item(self, item_id: str, payload: dict | None = None, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.plans.update_item, persona_id, item_id,
                                {"action": "skip", "reason": (payload or {}).get("reason", "Skipped by user")},
                                actor="user", reason=(payload or {}).get("reason", "Skipped by user"))

    @register.api(method="GET", path="/v1/day-state/{day}")
    async def api_day_state(self, day: str, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.plans.day_state, persona_id, day)

    @register.api(method="POST", path="/v1/day-state/{day}")
    async def api_save_day_state(self, day: str, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.plans.set_day_state, persona_id, day, payload, "user", "WebUI edit")

    @register.api(method="GET", path="/v1/experiences")
    async def api_experiences(self, date: str = "", item_id: str = "", limit: int = 30, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.plans.experiences, persona_id, date or None, item_id, limit)

    @register.api(method="POST", path="/v1/experiences")
    async def api_add_experience(self, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        day = payload.get("date") or await self.runtime.plans.current_date(persona_id)
        return await self._call(self.runtime.plans.record_experience, persona_id, day,
                                str(payload.get("content", "")), kind=payload.get("kind", "note"),
                                item_id=payload.get("item_id", ""))

    @register.api(method="GET", path="/v1/config")
    async def api_config(self, persona: str = ""):
        persona_id = await self._persona(persona)
        return {"config": await self.runtime.store.get_config(persona_id),
                "revision": await self.runtime.store.config_revision(persona_id)}

    @register.api(method="PUT", path="/v1/config")
    async def api_update_config(self, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        patch = payload.get("patch") or {key: value for key, value in payload.items() if key != "expected_revision"}
        return await self._call(webapi.update_config, self.runtime, persona_id, patch,
                                int(payload.get("expected_revision", 0)))

    @register.api(method="GET", path="/v1/day-types")
    async def api_day_types(self, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self.runtime.store.list_day_types(persona_id)

    @register.api(method="POST", path="/v1/day-types")
    async def api_save_day_type(self, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.store.save_day_type, persona_id, payload)

    @register.api(method="DELETE", path="/v1/day-types/{identifier}")
    async def api_delete_day_type(self, identifier: str, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(self.runtime.store.delete_day_type, persona_id, identifier)

    @register.api(method="GET", path="/v1/sessions")
    async def api_sessions(self, kind: str = "execution", persona: str = ""):
        persona_id = await self._persona(persona)
        return await self.runtime.policy.session_options(persona_id, kind)

    @register.api(method="GET", path="/v1/weather/current")
    async def api_weather(self, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self.runtime.weather.summary(persona_id)

    @register.api(method="POST", path="/v1/weather/geocode")
    async def api_geocode(self, payload: dict):
        return await self._call(self.runtime.weather.geocode, str(payload.get("name", "")))

    @register.api(method="POST", path="/v1/weather/preview")
    async def api_weather_preview(self, payload: dict):
        async def preview():
            if payload.get("mode") == "virtual":
                return self.runtime.weather.virtual(await self._persona(""), payload.get("virtual", {}))
            return await self.runtime.weather._fetch(payload["provider"], payload["location"], 5)
        return await self._call(preview)

    @register.api(method="GET", path="/v1/avatar")
    async def api_avatar(self, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self.runtime.avatars.current(persona_id)

    @register.api(method="POST", path="/v1/assets")
    async def api_upload(self, file: UploadFile = File(...), persona: str = ""):
        persona_id = await self._persona(persona)
        content = await file.read(5 * 1024 * 1024 + 1)
        return await self._call(webapi.asset_service(self.runtime).save_bytes, persona_id, content)

    @register.api(method="GET", path="/v1/assets/{identifier}")
    async def api_asset(self, identifier: str, persona: str = ""):
        persona_id = await self._persona(persona)
        async def load():
            row = await webapi.asset_service(self.runtime).get(persona_id, identifier)
            if not row:
                raise KRDError("not_found", "Asset not found")
            return FileResponse(row["resolved_path"], media_type=row["mime"], headers={"Cache-Control": "private, max-age=86400"})
        return await self._call(load)

    @register.api(method="DELETE", path="/v1/assets/{identifier}")
    async def api_delete_asset(self, identifier: str, persona: str = ""):
        persona_id = await self._persona(persona)
        async def remove():
            row = await webapi.asset_service(self.runtime).get(persona_id, identifier)
            if not row:
                raise KRDError("not_found", "Asset not found")
            config = await self.runtime.store.get_config(persona_id)
            used_by_plan = await self.runtime.store.one("SELECT id FROM blocks WHERE cover_asset_id=? LIMIT 1", (identifier,))
            if config["appearance"].get("avatar_asset_id") == identifier or used_by_plan:
                raise KRDError("asset_in_use", "Remove the avatar or block cover reference before deleting this image")
            await self.runtime.store.execute("DELETE FROM assets WHERE id=?", (identifier,))
            row["resolved_path"].unlink(missing_ok=True)
            return {"deleted": True}
        return await self._call(remove)

    @register.api(method="GET", path="/v1/templates")
    async def api_templates(self, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self.runtime.store.get_setting(f"templates:{persona_id}", [])

    @register.api(method="POST", path="/v1/templates")
    async def api_save_template(self, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        async def save():
            name = str(payload.get("name", "")).strip()[:100]
            plan = payload.get("plan")
            if not name or not isinstance(plan, dict):
                raise KRDError("invalid_template", "Template requires a name and plan")
            templates = await self.runtime.store.get_setting(f"templates:{persona_id}", [])
            entry = {"id": payload.get("id") or new_id("tpl"), "name": name,
                     "description": str(payload.get("description", ""))[:500], "plan": plan,
                     "custom": True, "created_at": now()}
            templates = [item for item in templates if item["id"] != entry["id"]]
            templates.append(entry)
            if len(templates) > 100 or len(json.dumps(templates, ensure_ascii=False)) > 2000000:
                raise KRDError("template_limit", "Custom templates exceed the storage limit")
            await self.runtime.store.put_setting(f"templates:{persona_id}", templates)
            return entry
        return await self._call(save)

    @register.api(method="DELETE", path="/v1/templates/{identifier}")
    async def api_delete_template(self, identifier: str, persona: str = ""):
        persona_id = await self._persona(persona)
        async def remove():
            templates = await self.runtime.store.get_setting(f"templates:{persona_id}", [])
            remaining = [item for item in templates if item["id"] != identifier]
            if len(remaining) == len(templates):
                raise KRDError("not_found", "Template not found")
            await self.runtime.store.put_setting(f"templates:{persona_id}", remaining)
            return {"deleted": True}
        return await self._call(remove)

    @register.api(method="GET", path="/v1/runs")
    async def api_runs(self, limit: int = 50, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self.runtime.store.all(
            "SELECT * FROM runs WHERE persona_id=? ORDER BY claimed_at DESC LIMIT ?",
            (persona_id, max(1, min(200, limit))))

    @register.api(method="GET", path="/v1/diagnostics")
    async def api_diagnostics(self):
        return await webapi.diagnostics(self.runtime)

    @register.api(method="GET", path="/v1/export")
    async def api_export(self, persona: str = ""):
        persona_id = await self._persona(persona)
        return await webapi.export_data(self.runtime, persona_id)

    @register.api(method="POST", path="/v1/import/preview")
    async def api_import_preview(self, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(webapi.import_preview, self.runtime, persona_id, payload)

    @register.api(method="POST", path="/v1/import/commit")
    async def api_import_commit(self, payload: dict, persona: str = ""):
        persona_id = await self._persona(persona)
        return await self._call(webapi.import_commit, self.runtime, persona_id, payload)

    @register.ws("/v1/events")
    async def api_events(self, websocket):
        await websocket.accept()
        self.runtime.ws_clients.add(websocket)
        try:
            await websocket.send_json({"type": "ready", "payload": {"time": __import__('time').time()}})
            while True:
                text = await websocket.receive_text()
                if text == "ping":
                    await websocket.send_json({"type": "pong", "payload": {"time": __import__('time').time()}})
        except Exception:
            pass
        finally:
            self.runtime.ws_clients.discard(websocket)
