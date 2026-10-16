import json
import os
import subprocess
import sys
from pathlib import Path


def test_partial_cleanup_recovery_retry_is_isolated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sandbox = tmp_path / "cleanup_sandbox"
    sandbox.mkdir()

    file_a = sandbox / "cleanup_a.tmp"
    file_b = sandbox / "cleanup_b.tmp"
    file_c = sandbox / "cleanup_c.tmp"

    for path in (file_a, file_b, file_c):
        path.write_text("temporary data", encoding="utf-8")

    # Simulate a partial side effect before a crash.
    file_a.unlink()
    file_b.unlink()
    assert not file_a.exists()
    assert not file_b.exists()
    assert file_c.exists()

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    state_path.write_text(
        json.dumps({
            "actions": [{
                "action": "free-disk-space",
                "priority": "high",
                "execution_mode": "automatic",
                "status": "executing",
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
                "execution_result": "partial-cleanup",
                "execution_started_at": "2000-01-01T00:00:00+00:00",
                "cleanup_targets": [str(file_a), str(file_b), str(file_c)],
            }]
        }, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    child_code = r'''
import json
from contextlib import contextmanager
from pathlib import Path

from judgment import audit, execution, lifecycle, recovery
from judgment.state_lock import state_lock as real_state_lock

state_dir = Path("state")
state_path = state_dir / "latest.json"

recovery.STATE_PATH = state_path
lifecycle.STATE_PATH = state_path
execution.STATE_PATH = state_path

audit.AUDIT_PATH = state_dir / "audit.json"
audit.AUDIT_TEMP_PATH = state_dir / "audit.tmp"
audit.AUDIT_LOCK_PATH = state_dir / "audit.lock"

@contextmanager
def isolated_state_lock(lock_path=None):
    path = lock_path if lock_path is not None else state_dir / "state.lock"
    with real_state_lock(path):
        yield

recovery.state_lock = isolated_state_lock
lifecycle.state_lock = isolated_state_lock

recovered = recovery.recover_interrupted_actions()
state = json.loads(state_path.read_text(encoding="utf-8"))
action = state["actions"][0]

assert "free-disk-space" in recovered
assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
assert action["retry_count"] == 0

retry = lifecycle.retry_failed_action("free-disk-space")
assert retry["status"] == "approved"
assert retry["retry_count"] == 1

start = execution.execute_action("free-disk-space")
assert start["status"] == "executing"

targets = [Path(p) for p in action["cleanup_targets"]]

# Idempotent cleanup: remove only targets that still exist.
for target in targets:
    if target.exists():
        target.unlink()

complete = execution.execute_action(
    "free-disk-space",
    result="partial-cleanup-recovered-success",
    complete=True,
)
assert complete["status"] == "executed"

final_state = json.loads(state_path.read_text(encoding="utf-8"))
final_action = final_state["actions"][0]
events = [
    event for event in audit.load_audit()
    if event.get("action") == "free-disk-space"
]

print(json.dumps({
    "recovered": recovered,
    "retry": retry,
    "start": start,
    "complete": complete,
    "action": final_action,
    "events": events,
}))
'''
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    result = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, (
        f"Child failed with exit code {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    output = json.loads(result.stdout.strip().splitlines()[-1])
    action = output["action"]
    events = output["events"]
    event_names = [event.get("event") for event in events]

    assert output["retry"]["retry_count"] == 1
    assert output["complete"]["status"] == "executed"
    assert action["status"] == "executed"
    assert action["execution_result"] == "partial-cleanup-recovered-success"
    assert action["retry_count"] == 1
    assert action["escalation_required"] is False

    assert "recovery-interrupted" in event_names
    assert "retry-approved" in event_names
    assert "execution-started" in event_names
    assert "execution-completed" in event_names

    assert not file_a.exists()
    assert not file_b.exists()
    assert not file_c.exists()
    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
