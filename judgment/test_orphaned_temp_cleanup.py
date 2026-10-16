import json
import os
import subprocess
import sys
from pathlib import Path


def test_orphaned_temp_does_not_override_approved_state(tmp_path):
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
    temp_path.write_text(
        json.dumps({
            "actions": [{
                "action": "free-disk-space",
                "status": "executing",
            }]
        }),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    original_temp = temp_path.read_bytes()

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    )
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from judgment.recovery import recover_interrupted_actions
print("RECOVERED:", recover_interrupted_actions())
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

    assert child.returncode == 0, (
        f"Recovery failed: {child.returncode}\\n"
        f"STDOUT:\\n{child.stdout}\\nSTDERR:\\n{child.stderr}"
    )

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    target = next(
        item for item in final_state["actions"]
        if item.get("action") == "free-disk-space"
    )
    assert target["status"] == "approved"

    # This test documents current temp-file behavior. Cleanup is a
    # separate implementation requirement, not an assumed guarantee.
    if temp_path.exists():
        assert temp_path.read_bytes() == original_temp
