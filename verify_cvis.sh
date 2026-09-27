#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")"

fail=0

run() {
    echo
    echo "============================================================"
    echo "=== $1"
    echo "============================================================"
    shift
    "$@" || fail=1
}

run "GIT STATUS" git status --short
run "LAST COMMIT" git log -1 --oneline

run "PYTEST" bash -lc 'source venv/bin/activate && pytest -q'

run "COMPILE" bash -lc '
python -m compileall -q backend agent.py cli state system_collector
'

run "DOCKER STATUS" docker compose ps

run "BACKEND HEALTH" bash -lc '
curl -fsS http://127.0.0.1:8000/health | python -m json.tool
'

run "ROOT" bash -lc '
test "$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/)" = "200"
'

run "OPENAPI" bash -lc '
curl -fsS http://127.0.0.1:8000/openapi.json |
python -c "
import sys,json
d=json.load(sys.stdin)
required=[
  \"/health\",
  \"/devices\",
  \"/devices/register\",
  \"/devices/{device_id}/heartbeat\",
  \"/devices/{device_id}/metrics\",
  \"/actions/available\",
  \"/actions/execute\",
  \"/auth/login\"
]
missing=[p for p in required if p not in d.get(\"paths\",{})]
assert not missing, f\"Missing routes: {missing}\"
print(f\"OK: {len(required)} required routes present\")
"
'

run "DEVICE ROUTES" bash -lc '
curl -fsS http://127.0.0.1:8000/devices | python -m json.tool
'

run "AVAILABLE ACTIONS" bash -lc '
curl -fsS http://127.0.0.1:8000/actions/available | python -m json.tool
'

run "BACKEND LOG ERRORS" bash -lc '
if docker logs synapse-backend 2>&1 |
   grep -Eiq "Traceback|Unhandled exception|ERROR.*exception|startup.*failed"; then
    echo "ERRORS FOUND IN BACKEND LOG"
    docker logs synapse-backend 2>&1 |
      grep -Ei "Traceback|Unhandled exception|ERROR.*exception|startup.*failed" |
      tail -50
    exit 1
else
    echo "No matching fatal/runtime errors found"
fi
'

run "PORTS" bash -lc '
ss -ltn | grep -E ":(8000|80|443|4430)\\b"
'

echo
echo "============================================================"
if [ "$fail" -eq 0 ]; then
    echo "=== CVIS VERIFICATION: PASS"
else
    echo "=== CVIS VERIFICATION: FAIL"
fi
echo "============================================================"

exit "$fail"
