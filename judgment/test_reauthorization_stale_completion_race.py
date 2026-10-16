import json
import os
import subprocess
import sys
from pathlib import Path


def test_reauthorization_stale_completion_race_isolated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    diagnostic = (
        repo_root
        / "judgment"
        / "diagnostic_reauthorization_stale_completion_race.py"
    )

    env = os.environ.copy()
    env["CVIS_DIAGNOSTIC_SANDBOX"] = "1"
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

    output = result.stdout
    assert "RESULT: PASS" in output
    assert "Exactly ONE Worker-B completion won." in output
    assert "All competing completions were blocked." in output
    assert "Stale Worker A could not delete C." in output

    state_path = tmp_path / "state" / "latest.json"
    audit_path = tmp_path / "state" / "audit.json"

    assert state_path.exists(), "Isolated durable state was not created."
    assert audit_path.exists(), "Isolated audit log was not created."

    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in state["actions"]
        if item.get("action") == "free-disk-space"
    )

    assert action["status"] == "executed"
    assert action["retry_count"] == 0
    generation_b = action["execution_generation"]
    assert generation_b > 1

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    events = [
        event for event in audit
        if (
            event.get("action") == "free-disk-space"
            and event.get("event") == "execution-completed"
            and str(event.get("result", "")).startswith("WORKER-B-")
        )
    ]

    assert len(events) == 1, (
        f"Expected exactly one successful Worker-B completion audit event; "
        f"found {len(events)}."
    )
