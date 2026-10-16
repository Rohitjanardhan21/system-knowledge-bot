import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys


def test_audit_failure_recovery_isolated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    initial_action = {
        "action": "free-disk-space",
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
        "execution_result": None,
        "execution_generation": 0,
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
    }
    state_path.write_text(
        json.dumps({"actions": [initial_action]}, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(repo_root)
        + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    )

    audit_failure_code = r'''
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import judgment.lifecycle as lifecycle

def failing_audit(*args, **kwargs):
    raise RuntimeError("simulated-audit-write-failure")

lifecycle.record_execution = failing_audit

action = {
    "action": "free-disk-space",
    "priority": "high",
    "execution_mode": "automatic",
    "status": "approved",
}

try:
    lifecycle.begin_execution(action)
except RuntimeError as exc:
    assert str(exc) == "simulated-audit-write-failure"
else:
    raise AssertionError("Expected the simulated audit failure")

state_path = Path("state/latest.json")
state = json.loads(state_path.read_text(encoding="utf-8"))
target = next(
    item for item in state["actions"]
    if item.get("action") == "free-disk-space"
)
assert target["status"] == "executing", target

# Simulate enough elapsed time for restart recovery to consider it stale.
target["execution_started_at"] = (
    datetime.now(timezone.utc) - timedelta(minutes=10)
).isoformat()
state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

print("PASS: audit failure left durable executing state")
'''

    child = subprocess.run(
        [sys.executable, "-c", audit_failure_code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 0, (
        f"Audit-failure subprocess failed.\n"
        f"STDOUT:\n{child.stdout}\nSTDERR:\n{child.stderr}"
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    interrupted = next(
        item for item in state["actions"]
        if item.get("action") == "free-disk-space"
    )
    assert interrupted["status"] == "executing"

    recovery_code = r'''
import json
from pathlib import Path
from judgment.recovery import recover_interrupted_actions

recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)
assert "free-disk-space" in recovered, recovered

state = json.loads(
    Path("state/latest.json").read_text(encoding="utf-8")
)
target = next(
    item for item in state["actions"]
    if item.get("action") == "free-disk-space"
)
assert target["status"] == "failed", target
assert target["execution_result"] == "interrupted-by-restart", target
print("PASS: interrupted execution recovered")
'''

    recovery = subprocess.run(
        [sys.executable, "-c", recovery_code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert recovery.returncode == 0, (
        f"Recovery subprocess failed.\n"
        f"STDOUT:\n{recovery.stdout}\nSTDERR:\n{recovery.stderr}"
    )

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    final_action = next(
        item for item in final_state["actions"]
        if item.get("action") == "free-disk-space"
    )
    assert final_action["status"] == "failed"
    assert final_action["execution_result"] == "interrupted-by-restart"

    audit_events = json.loads(audit_path.read_text(encoding="utf-8"))
    assert isinstance(audit_events, list), audit_events
    assert any(
        isinstance(event, dict)
        and event.get("action") == "free-disk-space"
        and "recover" in str(event.get("event", "")).lower()
        for event in audit_events
    ), audit_events
