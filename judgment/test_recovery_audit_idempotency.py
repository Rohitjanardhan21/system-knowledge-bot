import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys


def test_recovery_audit_is_idempotent_in_isolated_directory(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()

    initial_state = {
        "actions": [
            {
                "action": "free-disk-space",
                "priority": "high",
                "execution_mode": "automatic",
                "status": "executing",
                "execution_result": None,
                "execution_generation": 1,
                "execution_started_at": started_at,
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
            }
        ]
    }

    (state_dir / "latest.json").write_text(
        json.dumps(initial_state, indent=2),
        encoding="utf-8",
    )
    (state_dir / "audit.json").write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    old_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(repo_root)
        + (os.pathsep + old_pythonpath if old_pythonpath else "")
    )

    child_code = r'''
import json
from pathlib import Path
from judgment.audit import load_audit
from judgment.recovery import recover_interrupted_actions

state_path = Path("state/latest.json")

initial_state = json.loads(state_path.read_text(encoding="utf-8"))
initial_action = next(
    item for item in initial_state["actions"]
    if item.get("action") == "free-disk-space"
)
assert initial_action["status"] == "executing"
before = load_audit()

print("1. INITIAL STATE: executing")
print("INITIAL AUDIT EVENTS:", len(before))

first_recovered = recover_interrupted_actions()
print("2. FIRST RECOVERY:", first_recovered)
assert "free-disk-space" in first_recovered, first_recovered

after_first = load_audit()
first_events = [
    event for event in after_first[len(before):]
    if event.get("event") == "recovery-interrupted"
    and event.get("action") == "free-disk-space"
]
assert len(first_events) == 1, first_events

state = json.loads(state_path.read_text(encoding="utf-8"))
action = next(
    item for item in state["actions"]
    if item.get("action") == "free-disk-space"
)
assert action["status"] == "failed", action
assert action["execution_result"] == "interrupted-by-restart", action
print("PASS: first recovery recorded exactly one event")

second_recovered = recover_interrupted_actions()
print("3. SECOND RECOVERY:", second_recovered)
assert "free-disk-space" not in second_recovered, second_recovered

after_second = load_audit()
second_events = [
    event for event in after_second[len(after_first):]
    if event.get("event") == "recovery-interrupted"
    and event.get("action") == "free-disk-space"
]
assert len(second_events) == 0, second_events

final_state = json.loads(state_path.read_text(encoding="utf-8"))
final_action = next(
    item for item in final_state["actions"]
    if item.get("action") == "free-disk-space"
)
assert final_action["status"] == "failed"
assert final_action["execution_result"] == "interrupted-by-restart"

print("PASS: second recovery added no duplicate event")
print("RESULT: recovery and audit are idempotent")
'''

    result = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"Isolated recovery idempotency test failed.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
