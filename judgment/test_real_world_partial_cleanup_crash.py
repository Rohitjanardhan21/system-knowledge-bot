import json
import os
import subprocess
import sys
from pathlib import Path


def test_partial_cleanup_crash_recovery_isolated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    diagnostic = (
        repo_root
        / "judgment"
        / "diagnostic_real_world_partial_cleanup_crash.py"
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
    assert "RECOVERY PRESERVED ACTUAL FILESYSTEM STATE" in result.stdout
    assert "Recovery did not consume retry budget." in result.stdout

    state_path = tmp_path / "state" / "latest.json"
    audit_path = tmp_path / "state" / "audit.json"
    sandbox = tmp_path / "state" / "real_world_partial_cleanup_sandbox"

    assert state_path.exists()
    assert audit_path.exists()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in state["actions"]
        if item.get("action") == "free-disk-space"
    )

    assert action["status"] == "failed"
    assert action["execution_result"] == "interrupted-by-restart"
    assert action["retry_count"] == 0
    assert action["max_retries"] == 2

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    recovery_events = [
        event for event in audit
        if (
            event.get("action") == "free-disk-space"
            and event.get("event") == "recovery-interrupted"
        )
    ]

    assert len(recovery_events) == 1
    assert recovery_events[0]["status"] == "failed"
    assert recovery_events[0]["result"] == "interrupted-by-restart"

    # The diagnostic removes its simulated cleanup files and sandbox.
    assert not sandbox.exists()
