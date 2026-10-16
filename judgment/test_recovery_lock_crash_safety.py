import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def test_crashed_recovery_lock_is_released_and_recovery_resumes(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    state_path = tmp_path / "state" / "latest.json"
    audit_path = tmp_path / "state" / "audit.json"
    state_path.parent.mkdir(parents=True)

    stale_time = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()

    state_path.write_text(
        json.dumps({
            "actions": [{
                "action": "free-disk-space",
                "status": "executing",
                "execution_result": None,
                "execution_started_at": stale_time,
                "execution_generation": 1,
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
            }]
        }, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    )
    env["PYTHONUTF8"] = "1"

    crash_code = r"""
import os
import sys
from pathlib import Path
from judgment.state_lock import state_lock

state_path = Path(sys.argv[1])
recovery_lock = state_path.with_suffix(".recovery.lock")

with state_lock(recovery_lock):
    print("RECOVERY LOCK ACQUIRED", flush=True)
    os._exit(99)
"""

    crashed = subprocess.run(
        [sys.executable, "-c", crash_code, str(state_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert crashed.returncode == 99, (
        f"Expected simulated crash:\n{crashed.stdout}\n{crashed.stderr}"
    )
    assert "RECOVERY LOCK ACQUIRED" in crashed.stdout

    recovery_code = r"""
import sys
from pathlib import Path
import judgment.audit as audit
import judgment.lifecycle as lifecycle
import judgment.recovery as recovery
import judgment.state_lock as state_lock_module

state_path = Path(sys.argv[1])
audit_path = Path(sys.argv[2])

audit.AUDIT_PATH = audit_path
audit.AUDIT_TEMP_PATH = audit_path.with_suffix(".tmp")
audit.AUDIT_LOCK_PATH = audit_path.with_suffix(".lock")
recovery.STATE_PATH = state_path
lifecycle.STATE_PATH = state_path

real_state_lock = state_lock_module.state_lock
shared_lock_path = state_path.parent / "state.lock"

def isolated_state_lock(lock_path=None):
    return real_state_lock(
        Path(lock_path) if lock_path is not None else shared_lock_path
    )

recovery.state_lock = isolated_state_lock
lifecycle.state_lock = isolated_state_lock

print("RECOVERED:", recovery.recover_interrupted_actions())
"""

    recovered = subprocess.run(
        [sys.executable, "-c", recovery_code,
         str(state_path), str(audit_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert recovered.returncode == 0, (
        f"Recovery failed after lock-holder crash:\n"
        f"{recovered.stdout}\n{recovered.stderr}"
    )

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    target = next(
        action for action in final_state["actions"]
        if action.get("action") == "free-disk-space"
    )

    assert target["status"] == "failed"
    assert target["execution_result"] == "interrupted-by-restart"

    final_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    matches = [
        event for event in final_audit
        if event.get("event") == "recovery-interrupted"
        and event.get("action") == "free-disk-space"
    ]
    assert len(matches) == 1
