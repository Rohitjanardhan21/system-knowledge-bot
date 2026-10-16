import json
import os
import subprocess
import sys
from pathlib import Path


def test_concurrent_world_cleanup_recovery_retry_isolated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    diagnostic = (
        repo_root
        / "judgment"
        / "diagnostic_real_world_concurrent_cleanup.py"
    )

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(repo_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    result = subprocess.run(
        [sys.executable, str(diagnostic)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )

    assert result.returncode == 0, (
        f"Diagnostic failed with exit code {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    assert "RESULT: PASS" in result.stdout
    assert "CRASH DID NOT PRODUCE FALSE SUCCESS" in result.stdout
    assert "RETRY REQUIRED EXPLICIT AUTHORIZATION" in result.stdout

    state_path = tmp_path / "state" / "latest.json"
    audit_path = tmp_path / "state" / "audit.json"
    sandbox = (
        tmp_path
        / "state"
        / "real_world_concurrent_cleanup_sandbox"
    )

    assert state_path.exists()
    assert audit_path.exists()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in state["actions"]
        if item.get("action") == "free-disk-space"
    )

    assert action["status"] == "executed"
    assert action["execution_result"] == "cleanup-reconciled-success"
    assert action["retry_count"] == 1
    assert action["escalation_required"] is False

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    events = [
        event for event in audit
        if event.get("action") == "free-disk-space"
    ]
    event_names = [event.get("event") for event in events]

    assert "recovery-interrupted" in event_names
    assert "retry-approved" in event_names
    assert "execution-completed" in event_names

    # The diagnostic performs cleanup; no sandbox should remain.
    assert not sandbox.exists()
