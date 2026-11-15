from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main(root: Path):
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["plugin_id"] == "kira_rhythm_Date"
    assert manifest["core_version"] == ">=3.1.2"
    python_files = list((root / "krd").glob("*.py")) + [root / "main.py"]
    source = "\n".join(path.read_text() for path in python_files)
    for banned in ("time.sleep(", "asyncio.run(", "auth=False", "message_types", "fetch_memory", "write_memory", "read_memory"):
        assert banned not in source, banned
    assert "ctx.get_plugin_data_dir()" in (root / "main.py").read_text()
    assert 'extra={"krd":' in source and "system_krd" in source
    assert "persist=False" in source
    assert 'name="rhythm_plan"' in (root / "main.py").read_text()
    assert 'name="rhythm_update"' in (root / "main.py").read_text()
    assert 'name="rhythm_view"' in (root / "main.py").read_text()
    assert "rhythm_complete" not in (root / "main.py").read_text()
    index = (root / "web" / "index.html").read_text()
    assert "/plugin-bridge.js" in index and "vendor/vue.global.prod.js" in index
    assert "http://" not in index and "https://" not in index
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', index)
    assert not any(script.startswith(("http://", "https://", "//")) for script in scripts)
    assert "web/preview.html" not in "\n".join(str(path) for path in root.rglob("*"))
    frontend = "\n".join(path.read_text() for path in (root / "web" / "js").glob("*.js"))
    app = (root / "web" / "js" / "app.js").read_text()
    assert "eval(" not in frontend and "new Function" not in frontend
    assert "weatherapi_key" not in frontend and "openweather_key" not in frontend
    assert "window.__krdApp = app.mount" not in frontend
    assert "location.search.includes('debug')" in frontend
    assert "delete payload.schema_version" in app and "delete payload.per_persona" in app
    assert "this.monthAnchor = state.selectedDate.slice(0, 7)" in app
    assert "this.monthAnchor = date.slice(0, 7)" in app
    assert "refresh=1&persona=" in app and "cache: method === 'GET' ? 'no-store'" in frontend
    assert "const payload = Object.fromEntries(allowed.map" in app
    assert "await runtime.scheduler.wake()" not in (root / "krd" / "tools.py").read_text()
    runtime_source = (root / "krd" / "runtime.py").read_text()
    assert "before_llm_response" not in runtime_source
    assert 'response.text_response = "<msg/>"' not in runtime_source
    assert not list(root.rglob("*.pyc"))
    assert not any(ord(char) > 0x1F000 for char in frontend), "emoji is forbidden in frontend"
    themes = (
        "tomato_rain", "tomato_greenhouse", "tomato_archive",
        "mint_coast", "mint_soda", "mint_arcade",
        "garnet_dusk", "garnet_alley", "garnet_pool",
        "xun_street", "xun_diner", "xun_rooftop",
        "hathor_garage", "hathor_roof", "hathor_store",
    )
    for theme in themes:
        assert (root / "assets" / "themes" / f"{theme}.webp").is_file(), theme
    for pet in ("tomato", "mint", "garnet", "xun", "hathor"):
        for pose in ("idle", "sit", "read", "eat", "drink", "sleep", "phone"):
            assert (root / "assets" / "pets" / f"{pet}_{pose}.webp").is_file(), f"{pet}_{pose}"
    assert "planning_review" in (root / "krd" / "config.py").read_text()
    required_bindings = {"settingsTab", "selectedDate", "selectedPlan", "dayStateEditor", "dayTypeEditor", "runs"}
    for name in required_bindings:
        assert re.search(rf"\b{name}\b", app), name
    for provider in ("open_meteo", "met_norway", "nws", "bright_sky", "weatherapi", "visualcrossing", "qweather", "weatherbit", "openweather"):
        assert provider in (root / "krd" / "weather.py").read_text(), provider
    print("RELEASE AUDIT OK", len(python_files), "Python modules", len(scripts), "local scripts")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
