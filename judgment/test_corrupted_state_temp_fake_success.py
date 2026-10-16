import json
import os
import subprocess
import sys
from pathlib import Path


def test_corrupt_state_does_not_promote_orphaned_fake_success(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    temp_path = state_dir / "latest.tmp"
    audit_path = state_dir / "audit.json"

    action_name = "free-disk-space"

    # The authoritative state is corrupt, while the orphaned temp
    # contains a structurally plausible but untrusted fake success.
    state_path.write_text(
        '{"actions": [INVALID CORRUPTED JSON',
        encoding="utf-8",
    )
    temp_path.write_text(
        json.dumps({
            "actions": [{
                "action": action_name,
                "status": "executed",
                "execution_result": "orphaned-fake-success",
                "execution_generation": 1,
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
            }]
        }),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    original_corrupt_bytes = state_path.read_bytes()
    original_temp_bytes = temp_path.read_bytes()

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    )
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    child_code = """
from judgment.recovery import recover_interrupted_actions
print("RECOVERED:", recover_interrupted_actions())
"""

    result = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, (
        f"Recovery subprocess failed: {result.returncode}\\n"
        f"STDOUT:\\n{result.stdout}\\nSTDERR:\\n{result.stderr}"
    )

    # Recovery must not accept the orphaned fake success.
    assert state_path.read_bytes() != b"", "Authoritative state unexpectedly empty"

    try:
        resulting_state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        resulting_state = None

    if resulting_state is not None:
        assert not any(
            action.get("action") == action_name
            and action.get("status") == "executed"
            and action.get("execution_result") == "orphaned-fake-success"
            for action in resulting_state.get("actions", [])
            if isinstance(action, dict)
        ), "Recovery promoted the orphaned fake success"

    # If recovery declines to repair corrupt state, both original files
    # may remain unchanged. If it does repair state, it still must not
    # manufacture the fake success.
    assert not (
        temp_path.exists()
        and temp_path.read_bytes() != original_temp_bytes
    ), "Unexpected mutation of the orphaned temp candidate"

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert isinstance(audit, list)
