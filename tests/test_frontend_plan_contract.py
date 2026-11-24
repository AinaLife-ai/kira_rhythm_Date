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


def test_settings_draft_normalizes_preview_and_partial_config():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    views = (WEB / "views.js").read_text(encoding="utf-8")
    fixture = (ROOT / "tests" / "web_fixture.js").read_text(encoding="utf-8")
    assert "calendar_context: { holiday: true" in app
    assert "this.draft.inject_agenda ??= true" in app
    assert "普通聊天附带待办清单" in views
    assert "待办清单最多字符数" in views
    assert "calendar_context" in fixture

def test_bottom_nav_uses_six_columns_without_wrapping():
    css = (ROOT / "web" / "css" / "nte.css").read_text(encoding="utf-8")
    assert ".main-nav { display:grid; grid-template-columns:repeat(6,minmax(0,1fr));" in css
    assert ".main-nav button:last-child" not in css
    views = (ROOT / "web" / "js" / "views.js").read_text(encoding="utf-8")
    assert "$root.draft.threads.empty_mode" in views
    assert "$root.draft.threads.empty_min" in views
    assert "$root.draft.threads.empty_max" in views
    assert "要求至少 {{ $root.draft.threads.empty_min }} 条（严格）" in views
