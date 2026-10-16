import json
import os
import subprocess
import sys
from pathlib import Path


def test_partial_cleanup_recovery_and_retry_isolated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    diagnostic = (
        repo_root
        / "judgment"
        / "diagnostic_real_world_partial_cleanup_retry.py"
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
    sandbox = state_dir / "real_world_retry_cleanup_sandbox"

    assert state_path.is_file()
    assert audit_path.is_file()
    assert not sandbox.exists(), "Diagnostic sandbox was not cleaned up"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    actions = [
        item for item in state["actions"]
        if item.get("action") == "free-disk-space"
    ]
    assert len(actions) == 1

    action = actions[0]
    assert action["status"] == "executed"
    assert action["execution_result"] == "remaining-cleanup-success"
    assert action["retry_count"] == 1
    assert action["max_retries"] == 2
    assert action["escalation_required"] is False

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    events = [
        event for event in audit
        if event.get("action") == "free-disk-space"
    ]
    names = [event.get("event") for event in events]

    assert names.count("recovery-interrupted") == 1
    assert names.count("retry-approved") == 1
    assert names.count("execution-started") == 2
    assert names.count("execution-completed") == 1
