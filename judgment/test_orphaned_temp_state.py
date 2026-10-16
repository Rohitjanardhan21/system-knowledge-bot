import json
import os
import subprocess
import sys
from pathlib import Path


def test_orphaned_temp_does_not_replace_authoritative_state(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    temp_path = state_dir / "latest.tmp"
    audit_path = state_dir / "audit.json"

    state_path.write_text(
        json.dumps({
            "actions": [{
                "action": "free-disk-space",
                "status": "approved",
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
            }]
        }),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")
    authoritative_before = state_path.read_bytes()

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    )
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    crash_writer = r"""
from pathlib import Path
import json
import os

state_path = Path("state/latest.json")
temp_path = state_path.with_suffix(".tmp")
state = json.loads(state_path.read_text(encoding="utf-8"))
state["actions"][0]["status"] = "executing"

with temp_path.open("w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
    f.flush()
    os.fsync(f.fileno())

os._exit(99)
"""

    child = subprocess.run(
        [sys.executable, "-c", crash_writer],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert child.returncode == 99, (
        f"Expected simulated crash exit 99; got {child.returncode}\n"
        f"{child.stdout}\n{child.stderr}"
    )
    assert temp_path.is_file()

    # The interrupted writer must not have replaced latest.json.
    assert state_path.read_bytes() == authoritative_before
    assert json.loads(state_path.read_text(encoding="utf-8"))["actions"][0]["status"] == "approved"
    assert json.loads(temp_path.read_text(encoding="utf-8"))["actions"][0]["status"] == "executing"

    # A fresh process must still read the authoritative approved state.
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json
from pathlib import Path
state = json.loads(Path("state/latest.json").read_text(encoding="utf-8"))
assert state["actions"][0]["status"] == "approved"
print("AUTHORITATIVE STATE PRESERVED")
""",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert "AUTHORITATIVE STATE PRESERVED" in check.stdout
