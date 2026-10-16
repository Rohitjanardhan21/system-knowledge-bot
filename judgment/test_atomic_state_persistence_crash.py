import json
import os
import subprocess
import sys
from pathlib import Path


def test_atomic_state_persistence_survives_crash_before_replace(tmp_path):
    state_path = tmp_path / "latest.json"
    temp_path = state_path.with_suffix(".tmp")

    original = {
        "actions": [{
            "action": "free-disk-space",
            "status": "executing",
            "execution_result": None,
        }]
    }
    state_path.write_text(json.dumps(original, indent=2), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]

    child_code = r"""
import os
import sys
from pathlib import Path

from judgment import lifecycle

state_path = Path(sys.argv[1])
lifecycle.STATE_PATH = state_path

state = {
    "actions": [{
        "action": "free-disk-space",
        "status": "executed",
        "execution_result": "simulated-success",
    }]
}

temp_path = state_path.with_suffix(".tmp")
with temp_path.open("w", encoding="utf-8") as f:
    import json
    json.dump(state, f, indent=2)
    f.flush()
    os.fsync(f.fileno())

def crash_before_replace(source, destination):
    print("SIMULATED CRASH BEFORE REPLACEMENT", flush=True)
    os._exit(99)

lifecycle.os.replace = crash_before_replace
os.replace(temp_path, state_path)
raise AssertionError("Simulated crash did not occur")
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
        f"Unexpected exit code: {child.returncode}\n"
        f"stdout:\n{child.stdout}\nstderr:\n{child.stderr}"
    )

    durable = json.loads(state_path.read_text(encoding="utf-8"))
    assert durable["actions"][0]["status"] == "executing"
    assert durable["actions"][0]["execution_result"] is None

    assert temp_path.exists()
    abandoned = json.loads(temp_path.read_text(encoding="utf-8"))
    assert abandoned["actions"][0]["status"] == "executed"
    assert abandoned["actions"][0]["execution_result"] == "simulated-success"

    assert state_path.is_relative_to(tmp_path)
    assert temp_path.is_relative_to(tmp_path)
