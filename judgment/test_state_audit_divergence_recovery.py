import json
import os
import subprocess
import sys
from pathlib import Path


def test_executed_state_without_completion_audit_is_reconciled(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"
    action_name = "free-disk-space"
    result = "STATE-AUDIT-DIVERGENCE"
    generation = "isolated-generation-1"

    # Simulate durable lifecycle state written before a crash,
    # with the corresponding completion audit still missing.
    state_path.write_text(
        json.dumps({
            "actions": [{
                "action": action_name,
                "status": "executed",
                "execution_result": result,
                "execution_generation": generation,
            }]
        }, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    child_code = r'''
import json
from contextlib import contextmanager
from pathlib import Path

from judgment import audit, recovery
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

recovered = recovery.recover_interrupted_actions()
state = json.loads(state_path.read_text(encoding="utf-8"))
events = audit.load_audit()

print(json.dumps({
    "recovered": recovered,
    "state": state,
    "audit": events,
}))
'''
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    child = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )

    output = json.loads(child.stdout.strip().splitlines()[-1])
    final_action = output["state"]["actions"][0]
    matching = [
        event for event in output["audit"]
        if event.get("action") == action_name
        and event.get("event") == "execution-completed"
        and event.get("result") == result
        and event.get("execution_generation") == generation
    ]

    assert final_action["status"] == "executed"
    assert final_action["execution_result"] == result
    assert final_action["execution_generation"] == generation
    assert len(matching) == 1, (
        "Recovery must restore exactly one matching completion audit event"
    )
    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
