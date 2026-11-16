from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_default_motion_and_boot_do_not_follow_system_reduction():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    effects = (WEB / "css/effects.css").read_text(encoding="utf-8")
    game = (WEB / "css/game.css").read_text(encoding="utf-8")
    nte = (WEB / "css/nte.css").read_text(encoding="utf-8")

    assert "savedMotion==='reduced'?'reduced':'full'" in html
    assert 'class="icon-button motion-button"' in html
    assert 'class="weather-chip"' in html and 'openWeatherSettings' in html
    assert 'prefers-reduced-motion' not in effects
    assert 'prefers-reduced-motion' not in game
    assert 'prefers-reduced-motion' not in nte
    assert 'html[data-motion="reduced"]' in effects
    assert 'html[data-motion="reduced"]' in nte
    assert ".boot-screen { display: none" not in game


def test_weather_only_chats_and_pet_accessories_are_gone():
    pet = (WEB / "js/pet.js").read_text(encoding="utf-8")
    choose = pet.split("chooseAction(force) {", 1)[1].split("pickIdle()", 1)[0]
    assert "this.weather ===" not in choose
    assert "setAction('umbrella'" not in pet
    assert "pet-umbrella" not in pet
    assert "isUmbrella" not in pet
    assert "pet-scarf" not in pet
    assert "sayChatter" in pet and "buildPetChatter" in pet
    assert "scheduleChatter(5200)" in pet


def test_crouch_keeps_its_new_cumulative_scale():
    css = (WEB / "css/nte.css").read_text(encoding="utf-8")
    assert "scale(.5565)" in css
    assert "scale(.7225)" in css


def test_pet_chatter_is_persona_specific_and_prefers_session_titles():
    script = r'''
import { buildPetChatter } from './web/js/pet-talk.js';
const plan = { blocks: [{ items: [
  { title: '出门散步', intent: '换一换节奏', state: 'scheduled', scheduled_at: 1794795480, target: 'qq:dm:1' },
  { title: '整理房间', intent: '把桌面收一收', state: 'scheduled', scheduled_at: 1794796000, target: 'qq:dm:2' },
]}]};
const sessions = [{ sid: 'qq:dm:1', title: '测试会话' }, { sid: 'qq:dm:2', title: '' }];
const variants = ['tomato', 'mint', 'garnet', 'xun', 'hathor'];
const output = { lines: [], named: null, fallback: null, weather: null, quiet: null };
for (const variant of variants) {
  for (let i = 0; i < 7; i += 1) {
    const result = buildPetChatter({ variant, plan, sessions, nextItem: plan.blocks[0].items[0], weather: 'off', rng: () => ((i * 31 + 7) % 83) / 83 });
    output.lines.push({ variant, text: result.text, tones: result.parts.map((part) => part.tone) });
  }
}
output.named = buildPetChatter({ variant: 'tomato', plan, sessions, nextItem: plan.blocks[0].items[0], preferredTopic: 'next', rng: () => 0.2 });
output.fallback = buildPetChatter({ variant: 'mint', plan, sessions, nextItem: plan.blocks[0].items[1], preferredTopic: 'session', rng: () => 0.2 });
output.weather = buildPetChatter({ variant: 'xun', plan, sessions, nextItem: plan.blocks[0].items[0], weather: 'rain', preferredTopic: 'weather', rng: () => 0.2 });
output.quiet = buildPetChatter({ variant: 'hathor', plan: null, weather: 'off', rng: () => 0.2 });
console.log(JSON.stringify(output));
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert len({line["variant"] for line in output["lines"]}) == 5
    assert all(line["text"] and "伞" not in line["text"] for line in output["lines"])
    assert all(not line["text"].rstrip().endswith("。") for line in output["lines"])
    assert all("count" in line["tones"] or "title" in line["tones"] for line in output["lines"])
    named = output["named"]
    assert "测试会话" in named["text"]
    assert "测试会话" in {part["text"] for part in named["parts"] if part["tone"] == "session"}
    fallback = output["fallback"]
    assert "qq:dm:2" in fallback["text"]
    assert "qq:dm:2" in {part["text"] for part in fallback["parts"] if part["tone"] == "session"}
    weather = output["weather"]
    assert weather["topic"] == "weather"
    assert "雨" in weather["text"]
    assert any(part["tone"] == "weather" for part in weather["parts"])
    assert output["quiet"]["text"]
