import json
import os
import subprocess
import sys
from pathlib import Path


def test_state_persistence_crash_before_replace_preserves_authoritative_state(
    tmp_path,
):
    state_path = tmp_path / "latest.json"
    temp_path = state_path.with_suffix(".tmp")

    original = {
        "actions": [{
            "action": "free-disk-space",
            "status": "approved",
            "execution_result": None,
        }]
    }
    state_path.write_text(json.dumps(original, indent=2), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]

    child_code = r"""
import json
import os
import sys
from pathlib import Path

from judgment import lifecycle

state_path = Path(sys.argv[1])
lifecycle.STATE_PATH = state_path

state = json.loads(state_path.read_text(encoding="utf-8"))
action = dict(state["actions"][0])
action["status"] = "executed"
action["execution_result"] = "simulated-success"

def crash_before_replace(source, destination):
    print("SIMULATED CRASH BEFORE os.replace()", flush=True)
    os._exit(99)

lifecycle.os.replace = crash_before_replace
lifecycle._persist_action(action)

raise AssertionError("Expected the simulated crash before replacement")
"""

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not existing_pythonpath
        else str(repo_root) + os.pathsep + existing_pythonpath
    )

    child = subprocess.run(
        [sys.executable, "-c", child_code, str(state_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert child.returncode == 99, (
        f"Unexpected child exit: {child.returncode}\n"
        f"stdout:\n{child.stdout}\nstderr:\n{child.stderr}"
    )

    # The authoritative file must remain valid and unchanged.
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    stored = persisted["actions"][0]
    assert stored["status"] == "approved"
    assert stored["execution_result"] is None

    # The temporary file was fully written before the simulated crash.
    assert temp_path.exists()
    temporary_state = json.loads(temp_path.read_text(encoding="utf-8"))
    temporary_action = temporary_state["actions"][0]
    assert temporary_action["status"] == "executed"
    assert temporary_action["execution_result"] == "simulated-success"

    # Both paths must be confined to the test's temporary directory.
    assert state_path.is_relative_to(tmp_path)
    assert temp_path.is_relative_to(tmp_path)
