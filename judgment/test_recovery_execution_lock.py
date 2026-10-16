import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _isolated_child_setup():
    return r"""
import os
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
"""


def test_recovery_and_execution_share_isolated_state_lock(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    state_path = tmp_path / "state" / "latest.json"
    audit_path = tmp_path / "state" / "audit.json"
    state_path.parent.mkdir(parents=True)

    stale_time = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()

    initial_state = {
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
    }

    state_path.write_text(
        json.dumps(initial_state, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    )
    env["PYTHONUTF8"] = "1"

    setup = _isolated_child_setup()

    recovery_code = setup + r"""
from judgment.recovery import recover_interrupted_actions
print("RECOVERY RESULT:", recover_interrupted_actions())
"""

    execution_code = setup + r"""
import json
from judgment.lifecycle import begin_execution

state = json.loads(state_path.read_text(encoding="utf-8"))
target = next(
    action for action in state["actions"]
    if action.get("action") == "free-disk-space"
)
print("EXECUTION RESULT:", json.dumps(begin_execution(target)))
"""

    recovery_process = subprocess.Popen(
        [sys.executable, "-c", recovery_code,
         str(state_path), str(audit_path)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    execution_process = subprocess.Popen(
        [sys.executable, "-c", execution_code,
         str(state_path), str(audit_path)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    recovery_stdout, recovery_stderr = recovery_process.communicate(
        timeout=20
    )
    execution_stdout, execution_stderr = execution_process.communicate(
        timeout=20
    )

    assert recovery_process.returncode == 0, (
        f"Recovery failed:\n{recovery_stdout}\n{recovery_stderr}"
    )
    assert execution_process.returncode == 0, (
        f"Execution failed:\n{execution_stdout}\n{execution_stderr}"
    )

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    target = next(
        action for action in final_state["actions"]
        if action.get("action") == "free-disk-space"
    )

    assert target["status"] == "failed"
    assert target["execution_result"] == "interrupted-by-restart"
    assert isinstance(final_state["actions"], list)

    final_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert any(
        event.get("event") == "recovery-interrupted"
        and event.get("action") == "free-disk-space"
        for event in final_audit
    )
