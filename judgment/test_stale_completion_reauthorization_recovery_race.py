import os
import subprocess
import sys
from pathlib import Path


def test_stale_completion_reauthorization_race_is_isolated(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    diagnostic = (
        repo_root
        / "judgment"
        / "diagnostic_stale_completion_reauthorization_recovery_race.py"
    )

    env = os.environ.copy()
    env["CVIS_DIAGNOSTIC_SANDBOX"] = "1"
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

    state_path = tmp_path / "state" / "latest.json"
    assert state_path.exists(), "Diagnostic did not create isolated state"

    import json

    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in state["actions"]
        if item.get("action", "").startswith(
            "stale-completion-reauthorization-race-"
        )
    )
    assert action["status"] == "executed"
    assert action.get("execution_generation") is not None
