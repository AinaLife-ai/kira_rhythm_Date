from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "js"


def test_plan_mutations_require_plan_payload():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    for marker in ("跳过失败：服务器没有返回计划",
                   "删除失败：服务器没有返回计划",
                   "保存失败：服务器没有返回计划"):
        assert marker in app
    assert app.count("if (!result?.plan) throw new Error") >= 3


def test_preview_fixture_implements_skip_and_plan_list():
    fixture = (ROOT / "tests" / "web_fixture.js").read_text(encoding="utf-8")
    assert "path.includes('/skip')" in fixture
    assert "item.state = 'cancelled'" in fixture
    assert "plan: data.plan, revision: data.plan?.revision" in fixture
    assert "return response(data.plan ? [data.plan] : [])" in fixture


def test_delete_controls_are_wired():
    views = (WEB / "views.js").read_text(encoding="utf-8")
    assert "跳过本次" in views
    assert "@delete=\"$emit('delete', $event)\"" in views
    assert "删除时段" in views
    assert "删除整天" in views

def test_pet_sleep_and_random_context_actions():
    pet = (WEB / "pet.js").read_text(encoding="utf-8")
    assert "nightSleepEligible" in pet
    assert "sleepSuppressedUntil" in pet
    assert "this.hour >= 23" in pet
    assert "wakeFromSleep" in pet
    assert "randomPool" in pet
    assert "sleepiness" not in pet
