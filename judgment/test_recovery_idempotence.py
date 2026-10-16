import json
import subprocess
import sys
from pathlib import Path


def test_recovery_is_idempotent_in_isolated_directory(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    state_path.write_text(
        json.dumps({
            "actions": [{
                "action": "free-disk-space",
                "status": "executing",
                "execution_started_at": "2000-01-01T00:00:00+00:00",
            }]
        }, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    child_code = r'''
import json
from pathlib import Path
from judgment import audit, recovery
from contextlib import contextmanager
from judgment.state_lock import state_lock as real_state_lock

state_path = Path("state/latest.json")
state_dir = state_path.parent
recovery.STATE_PATH = state_path
audit.AUDIT_PATH = state_dir / "audit.json"
audit.AUDIT_TEMP_PATH = state_dir / "audit.tmp"
audit.AUDIT_LOCK_PATH = state_dir / "audit.lock"

@contextmanager
def isolated_state_lock(lock_path=None):
    path = lock_path if lock_path is not None else state_dir / "state.lock"
    with real_state_lock(path):
        yield

recovery.state_lock = isolated_state_lock

result = recovery.recover_interrupted_actions()
print(json.dumps({
    "result": result,
    "state": json.loads(state_path.read_text(encoding="utf-8")),
}))
'''
    env = __import__("os").environ.copy()
    env["PYTHONPATH"] = str(repo_root) + (
        __import__("os").pathsep + env["PYTHONPATH"]
        if env.get("PYTHONPATH") else ""
    )

    def run_recovery():
        return subprocess.run(
            [sys.executable, "-c", child_code],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

    first = run_recovery()
    first_result = json.loads(first.stdout.strip().splitlines()[-1])
    assert "free-disk-space" in first_result["result"]

    first_action = first_result["state"]["actions"][0]
    assert first_action["status"] == "failed"
    assert first_action["execution_result"] == "interrupted-by-restart"
    first_completed_at = first_action["execution_completed_at"]

    second = run_recovery()
    second_result = json.loads(second.stdout.strip().splitlines()[-1])
    assert second_result["result"] == []

    second_action = second_result["state"]["actions"][0]
    assert second_action["status"] == "failed"
    assert second_action["execution_result"] == "interrupted-by-restart"
    assert second_action["execution_completed_at"] == first_completed_at

    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
