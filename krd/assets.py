from __future__ import annotations

import asyncio
import hashlib
import io
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from .models import KRDError, new_id, now
from .store import Store

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_SIDE = 4096


class AssetService:
    def __init__(self, store: Store, data_dir: Path):
        self.store = store
        self.root = Path(data_dir) / "assets"
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_lock = asyncio.Lock()

    @staticmethod
    def _normalize(content: bytes) -> tuple[bytes, int, int]:
        try:
            image = Image.open(io.BytesIO(content))
            if image.width <= 0 or image.height <= 0 or image.width * image.height > 32_000_000:
                raise KRDError("invalid_image_dimensions", "Image dimensions exceed the 32 MP safety limit")
            image.load()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise KRDError("invalid_image", "Uploaded content is not a valid image") from exc
        has_alpha = image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)
        image = image.convert("RGBA" if has_alpha else "RGB")
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=86, method=4)
        return buffer.getvalue(), image.width, image.height

    async def save_bytes(self, persona_id: str, content: bytes, *, mime: str = "image/webp") -> dict[str, Any]:
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise KRDError("invalid_image_size", "Image must be non-empty and at most 5 MiB")
        normalized, width, height = await asyncio.to_thread(self._normalize, content)
        digest = hashlib.sha256(normalized).hexdigest()
        async with self._write_lock:
            existing = await self.store.one("SELECT * FROM assets WHERE persona_id=? AND hash=?", (persona_id, digest))
            if existing:
                return self.public(existing)
            identifier = new_id("img")
            # Physical files are persona-namespaced, so deleting one persona's
            # asset can never break another persona's identical image.
            persona_dir = self.root / hashlib.sha256(persona_id.encode()).hexdigest()[:24]
            await asyncio.to_thread(persona_dir.mkdir, parents=True, exist_ok=True)
            path = persona_dir / f"{digest}.webp"
            try:
                await asyncio.to_thread(path.write_bytes, normalized)
                await self.store.execute(
                    "INSERT INTO assets(id,persona_id,hash,path,mime,width,height,size,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (identifier, persona_id, digest, str(path), "image/webp", width, height, len(normalized), now()))
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            row = await self.store.one("SELECT * FROM assets WHERE id=?", (identifier,))
            return self.public(row)

    async def import_path(self, persona_id: str, path: Path) -> dict[str, Any]:
        path = Path(path)
        if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
            raise KRDError("invalid_image_size", "Image is missing or too large")
        return await self.save_bytes(persona_id, await asyncio.to_thread(path.read_bytes))

    @staticmethod
    def public(row: dict[str, Any]) -> dict[str, Any]:
        from urllib.parse import quote
        return {"id": row["id"], "hash": row["hash"], "url": f"/api/plugin/kira_rhythm_Date/v1/assets/{row['id']}?persona={quote(row['persona_id'])}&v={row['hash'][:16]}",
                "mime": row["mime"], "width": row["width"], "height": row["height"], "size": row["size"]}

    async def get(self, persona_id: str, identifier: str) -> dict[str, Any] | None:
        row = await self.store.one("SELECT * FROM assets WHERE persona_id=? AND id=?", (persona_id, identifier))
        if not row:
            return None
        path = Path(row["path"]).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            raise KRDError("invalid_asset_path", "Asset path is invalid")
        return {**row, "resolved_path": path}
