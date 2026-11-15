from __future__ import annotations

import io

import pytest
from PIL import Image

from krd.assets import AssetService
from krd.store import Store
from krd.weather import WeatherService


@pytest.mark.asyncio
async def test_virtual_weather_is_reproducible(tmp_path):
    store = Store(tmp_path / "db")
    await store.initialize()
    service = WeatherService(store, None)
    config = {"seed": "fixed", "climate": "floating_city", "location": "云上城"}
    first = service.virtual("persona-a", config)
    second = service.virtual("persona-a", config)
    other = service.virtual("persona-b", config)
    assert first == second
    assert first["location"] == "云上城" and first["source"] == "virtual"
    assert first != other
    await store.close()


@pytest.mark.asyncio
async def test_images_are_reencoded_and_validated(tmp_path):
    store = Store(tmp_path / "db")
    await store.initialize()
    service = AssetService(store, tmp_path)
    source = Image.new("RGBA", (20, 20), (255, 100, 180, 100))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")
    result = await service.save_bytes("persona-a", buffer.getvalue())
    row = await service.get("persona-a", result["id"])
    assert row["mime"] == "image/webp" and row["resolved_path"].is_file()
    assert result["id"] in service.public(row)["url"] and "persona=persona-a" in service.public(row)["url"]
    with pytest.raises(Exception):
        await service.save_bytes("persona-a", b"not an image")
    await store.close()
