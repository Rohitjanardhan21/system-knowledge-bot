import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys


def test_recovery_is_idempotent_in_isolated_directory(tmp_path):
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

    state_path = state_dir / "latest.json"
    state_path.write_text(
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
from judgment.recovery import recover_interrupted_actions

state_path = Path("state/latest.json")

def read_action():
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return next(
        item for item in state["actions"]
        if item.get("action") == "free-disk-space"
    )

initial = read_action()
assert initial["status"] == "executing", initial
print("1. INITIAL STATE: executing")

first_recovered = recover_interrupted_actions()
print("2. FIRST RECOVERY:", first_recovered)
assert "free-disk-space" in first_recovered, first_recovered

first = read_action()
first_status = first.get("status")
first_result = first.get("execution_result")
first_completed_at = first.get("execution_completed_at")

assert first_status == "failed", first
assert first_result == "interrupted-by-restart", first
assert first_completed_at is not None, first
print("PASS: executing -> failed")

second_recovered = recover_interrupted_actions()
print("3. SECOND RECOVERY:", second_recovered)
assert "free-disk-space" not in second_recovered, second_recovered

final = read_action()
assert final.get("status") == first_status, final
assert final.get("execution_result") == first_result, final
assert final.get("execution_completed_at") == first_completed_at, final

print("PASS: second recovery made no additional transition")
print("RESULT: recovery is idempotent")
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
