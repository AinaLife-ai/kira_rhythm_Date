#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FW_312=${FW_312:-/var/minis/shared/kira312}
FW_320=${FW_320:-/var/minis/shared/kira320}
for FW in "$FW_312" "$FW_320"; do
  echo "=== KRD $FW ==="
  cd "$FW"
  PYTHONPATH="$FW:$ROOT" python3 -m pytest -q "$ROOT/tests/test_timeutils.py" "$ROOT/tests/test_scheduler.py" "$ROOT/tests/test_weather_assets.py" "$ROOT/tests/test_cache.py" "$ROOT/tests/test_domain_rules.py" "$ROOT/tests/test_avatar_planning.py"
  PYTHONPATH="$FW" python3 "$ROOT/tests/framework_smoke.py" "$FW" "$ROOT"
  PYTHONPATH="$FW" python3 "$ROOT/tests/framework_e2e.py" "$FW" "$ROOT"
done
cd "$ROOT"
find "$ROOT" -type d -name '__pycache__' -exec rm -rf {} +
python3 tests/audit_contract.py .
python3 -m pyflakes main.py krd/*.py
for file in web/js/*.js; do node --check "$file"; done
echo 'ALL KRD CHECKS PASSED'
