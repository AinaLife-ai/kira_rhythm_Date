from __future__ import annotations

import asyncio
import io
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from PIL import Image

from krd.assets import AssetService
from krd.avatars import AvatarService
from krd.weather import WeatherService
from .fakes import FakeRuntime


@pytest_asyncio.fixture
async def runtime(tmp_path):
    value = FakeRuntime(tmp_path)
    await value.store.initialize()
    yield value
    await value.close()


def image_bytes(color=(140, 120, 240)):
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_concurrent_identical_upload_is_deduplicated(runtime):
    service = AssetService(runtime.store, runtime.store.path.parent)
    rows = await asyncio.gather(*[service.save_bytes("persona-a", image_bytes()) for _ in range(12)])
    assert len({row["id"] for row in rows}) == 1
    assert len(await runtime.store.all("SELECT * FROM assets WHERE persona_id='persona-a'")) == 1


@pytest.mark.asyncio
async def test_identical_images_have_persona_specific_physical_files(runtime):
    service = AssetService(runtime.store, runtime.store.path.parent)
    first = await service.save_bytes("persona-a", image_bytes())
    second = await service.save_bytes("persona-b", image_bytes())
    one = await service.get("persona-a", first["id"])
    two = await service.get("persona-b", second["id"])
    assert one["hash"] == two["hash"]
    assert one["resolved_path"] != two["resolved_path"]
    assert one["resolved_path"].is_file() and two["resolved_path"].is_file()


@pytest.mark.asyncio
async def test_failed_forced_avatar_refresh_keeps_last_good_image(runtime):
    service = AvatarService(runtime.store, runtime.ctx, runtime.store.path.parent)
    original = await service.assets.save_bytes("persona-a", image_bytes())
    await runtime.store.put_setting("avatar:persona-a:qq", {"asset_id": original["id"], "fetched_at": __import__("time").time()})
    service._from_adapter = AsyncMock(side_effect=TimeoutError("offline"))
    result = await service.current("persona-a", force_refresh=True)
    assert result["id"] == original["id"] and result["stale"] is True


@pytest.mark.asyncio
async def test_bootstrap_weather_mode_never_calls_network(runtime):
    service = WeatherService(runtime.store, runtime.ctx)
    await runtime.store.update_config("persona-a", {"weather": {
        "mode": "real", "locations": {"default": {"latitude": 31.2, "longitude": 121.5}},
    }}, 0)
    service._fetch = AsyncMock()
    result = await service.summary("persona-a", allow_network=False)
    assert result["real"]["status"] == "pending"
    service._fetch.assert_not_called()


@pytest.mark.asyncio
async def test_weather_http_error_is_not_cached_as_weather(runtime):
    service = WeatherService(runtime.store, runtime.ctx)
    class FailureResponse:
        def raise_for_status(self):
            raise RuntimeError("HTTP 503")
    client = type("Client", (), {"get": AsyncMock(return_value=FailureResponse())})()
    with pytest.raises(RuntimeError, match="503"):
        await service._get(client, "https://example.test")


@pytest.mark.asyncio
async def test_weather_credentials_are_persona_scoped_and_merged(runtime):
    service = WeatherService(runtime.store, runtime.ctx)
    await service.save_credentials("persona-a", {"providers": {"weatherapi": {"weatherapi_key": "a-key"}}})
    await service.save_credentials("persona-a", {"providers": {"qweather": {"qweather_key": "q-key"}}})
    status = await service.credential_status("persona-a")
    assert status["providers"]["weatherapi"]["weatherapi_key"] is True
    assert status["providers"]["qweather"]["qweather_key"] is True
    assert await service._credential("weatherapi_key", "persona-a") == "a-key"
    assert await service._credential("qweather_key", "persona-a") == "q-key"
    persona_b = await service.credential_status("persona-b")
    assert persona_b["providers"]["weatherapi"]["weatherapi_key"] is False
