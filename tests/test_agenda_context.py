import pytest

from tests.fakes import FakeRuntime
from krd.weather import WeatherService


@pytest.mark.asyncio
async def test_normal_context_has_state_weather_agenda(tmp_path):
    rt = FakeRuntime(tmp_path)
    await rt.store.initialize()
    day = await rt.plans.current_date("persona-a")
    await rt.plans.apply_plan("persona-a", {"date": day, "title": "T", "blocks": [{"title": "B", "items": [
        {"title": "A", "instruction": "ia", "schedule": {"type": "exact", "at": "18:00"}, "target": "qq:dm:10001"},
        {"title": "C", "instruction": "ic", "schedule": {"type": "exact", "at": "20:00"}, "target": "qq:dm:10001"}]}]}, actor="user", expected_revision=0)
    await rt.store.update_config("persona-a", {"weather": {"mode": "virtual", "virtual": {"seed": "x", "climate": "island", "location": "海"}}}, 0)
    rt.context_builder.weather = WeatherService(rt.store, rt.ctx)
    text = await rt.context_builder.compact_state("persona-a", config=await rt.store.get_config("persona-a"), current_sid="qq:dm:10001")
    assert "[KRD DayState]" in text and "[KRD Weather]" in text and "[KRD Agenda]" in text
    assert "now:" in text and "next:" in text and "progress: 0/2" in text
    assert "-> qq:dm:10001" not in text
    text_other = await rt.context_builder.compact_state("persona-a", config=await rt.store.get_config("persona-a"), current_sid="qq:dm:99999")
    assert "-> qq:dm:10001" in text_other
    assert text.count("#") >= 2
    await rt.close()
