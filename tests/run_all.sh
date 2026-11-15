#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FW_312=${FW_312:-/var/minis/shared/kira312}
FW_320=${FW_320:-/var/minis/shared/kira320}
for FW in "$FW_312" "$FW_320"; do
  echo "=== KRD $FW ==="
  cd "$FW"
  PYTHONPATH="$FW:$ROOT" python3 -m pytest -q "$ROOT/tests"
  PYTHONPATH="$FW" python3 "$ROOT/tests/framework_smoke.py" "$FW" "$ROOT"
  PYTHONPATH="$FW" python3 "$ROOT/tests/framework_e2e.py" "$FW" "$ROOT"
  PYTHONPATH="$FW" python3 "$ROOT/tests/api_integration.py" "$FW" "$ROOT"
  PYTHONPATH="$ROOT:$FW" python3 -P -m tests.stress_audit
done
cd "$ROOT"
find "$ROOT" -type d -name '__pycache__' -exec rm -rf {} +
python3 tests/audit_contract.py .
python3 -m pyflakes main.py krd/*.py tests/*.py
for file in web/js/*.js; do node --check "$file"; done
echo 'ALL KRD CHECKS PASSED'
