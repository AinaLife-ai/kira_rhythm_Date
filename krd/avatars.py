from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from .assets import AssetService
from .models import now
from .store import Store


class AvatarService:
    def __init__(self, store: Store, ctx, data_dir: Path):
        self.store = store
        self.ctx = ctx
        self.assets = AssetService(store, data_dir)
        self._refresh_lock = asyncio.Lock()

    async def current(self, persona_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        config = await self.store.get_config(persona_id)
        appearance = config["appearance"]
        asset_id = appearance.get("avatar_asset_id")
        if asset_id:
            row = await self.store.one("SELECT * FROM assets WHERE persona_id=? AND id=?", (persona_id, asset_id))
            if row:
                return {"source": "upload", **self.assets.public(row)}
        source = appearance.get("avatar_source", "auto")
        if source == "auto":
            adapters = self.ctx.adapter_mgr.get_adapters() if hasattr(self.ctx.adapter_mgr, "get_adapters") else {}
            order = appearance.get("avatar_adapter_order") or list(adapters)
            for name in order:
                adapter = adapters.get(name) or self.ctx.adapter_mgr.get_adapter(name)
                if not adapter or not getattr(adapter, "is_running", True):
                    continue
                cache_key = f"avatar:{persona_id}:{name}"
                cached = await self.store.get_setting(cache_key, {})
                row = None
                if cached.get("asset_id"):
                    row = await self.store.one(
                        "SELECT * FROM assets WHERE persona_id=? AND id=?", (persona_id, cached["asset_id"]))
                fresh = bool(row and now() - cached.get("fetched_at", 0) < 86400)
                if fresh and not force_refresh:
                    return {"source": f"adapter:{name}", **self.assets.public(row)}
                try:
                    async with self._refresh_lock:
                        result = await self._from_adapter(persona_id, name, adapter)
                        if result:
                            await self.store.put_setting(cache_key, {"asset_id": result["id"], "fetched_at": now()})
                            return result
                except Exception:
                    # A failed foreground refresh must not replace a working
                    # avatar with a builtin/persona fallback or blank image.
                    if row:
                        return {"source": f"adapter:{name}", "stale": True, **self.assets.public(row)}
                    continue
                if row:
                    return {"source": f"adapter:{name}", "stale": True, **self.assets.public(row)}
        try:
            path = await self.ctx.persona_mgr.get_reference_image(persona_id)
            if path:
                row = await self.assets.import_path(persona_id, path)
                return {"source": "persona_reference", **row}
        except Exception:
            pass
        return {"source": "builtin", "url": "/static/plugin/kira_rhythm_Date/assets/avatar.svg"}

    async def _from_adapter(self, persona_id: str, name: str, adapter) -> dict[str, Any] | None:
        platform = str(getattr(getattr(adapter, "info", None), "platform", "")).lower()
        if platform == "qq":
            config = getattr(adapter, "config", {}) or {}
            self_id = config.get("self_id") or config.get("bot_pid")
            if not self_id:
                bot = getattr(adapter, "bot", None)
                getter = getattr(bot, "get_login_info", None)
                if getter:
                    response = await getter()
                    self_id = response.get("data", {}).get("user_id") or response.get("user_id")
            if not self_id:
                return None
            url = f"https://q1.qlogo.cn/g?b=qq&nk={self_id}&s=640"
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content
            row = await self.assets.save_bytes(persona_id, content)
            return {"source": f"adapter:{name}", **row}
        # Optional adapters are feature-detected, never invoked through a made-up common API.
        bot = getattr(adapter, "bot", None)
        user = getattr(bot, "user", None) or getattr(bot, "get_me", None)
        avatar = getattr(user, "display_avatar", None)
        url = getattr(avatar, "url", None)
        if url:
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                response = await client.get(str(url))
                response.raise_for_status()
            row = await self.assets.save_bytes(persona_id, response.content)
            return {"source": f"adapter:{name}", **row}
        return None
