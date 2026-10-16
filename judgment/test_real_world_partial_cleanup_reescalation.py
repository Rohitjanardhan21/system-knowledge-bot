import json
import os
import subprocess
import sys
from pathlib import Path


def test_partial_cleanup_retry_reescalation_isolated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    diagnostic = (
        repo_root
        / "judgment"
        / "diagnostic_real_world_partial_cleanup_reescalation.py"
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, str(diagnostic)],
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
        f"Diagnostic failed with exit code {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "RESULT: PASS" in result.stdout

    state_dir = tmp_path / "state"
    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"
    sandbox = state_dir / "real_world_reescalation_sandbox"

    assert state_path.is_file(), "Isolated state file was not created"
    assert audit_path.is_file(), "Isolated audit file was not created"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    actions = [
        action for action in state["actions"]
        if action.get("action") == "free-disk-space"
    ]
    assert len(actions) == 1

    action = actions[0]
    assert action["status"] == "failed"
    assert action["retry_count"] == 2
    assert action["max_retries"] == 2
    assert action["escalation_required"] is True

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    events = [
        event for event in audit
        if event.get("action") == "free-disk-space"
    ]
    event_names = [event.get("event") for event in events]

    assert event_names.count("recovery-interrupted") == 1
    assert event_names.count("retry-approved") == 2
    assert event_names.count("retry-blocked") == 1
    assert event_names.count("execution-started") == 3

    assert not sandbox.exists(), "Diagnostic sandbox was not cleaned up"
