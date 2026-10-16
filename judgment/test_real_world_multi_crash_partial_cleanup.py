import json
import os
import subprocess
import sys
from pathlib import Path


def test_multi_crash_partial_cleanup_retry_and_reescalation_isolated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    diagnostic = (
        repo_root
        / "judgment"
        / "diagnostic_real_world_multi_crash_partial_cleanup.py"
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
        timeout=60,
    )

    assert result.returncode == 0, (
        f"Diagnostic failed with exit code {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    assert "RESULT: PASS" in result.stdout
    assert "SECOND CRASH DID NOT RESET RETRY COUNT" in result.stdout
    assert "RETRY EXHAUSTION RE-ESCALATED THE ACTION" in result.stdout

    state_path = tmp_path / "state" / "latest.json"
    audit_path = tmp_path / "state" / "audit.json"
    sandbox = tmp_path / "state" / "real_world_multi_crash_cleanup_sandbox"

    assert state_path.exists()
    assert audit_path.exists()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in state["actions"]
        if item.get("action") == "free-disk-space"
    )

    assert action["status"] == "failed"
    assert action["retry_count"] == 2
    assert action["max_retries"] == 2
    assert action["escalation_required"] is True
    assert action["execution_result"] == "final-cleanup-permission-denied"

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    events = [
        event for event in audit
        if event.get("action") == "free-disk-space"
    ]
    event_names = [event.get("event") for event in events]

    assert event_names.count("recovery-interrupted") == 2
    assert event_names.count("retry-approved") == 2
    assert event_names.count("execution-started") >= 3
    assert "retry-blocked" in event_names

    # The diagnostic should remove its temporary sandbox.
    assert not sandbox.exists()
