from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


def test_interrupted_action_recovery_persists_state_and_audit(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"
    action_name = "free-disk-space"
    started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()

    state_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "action": action_name,
                        "priority": "high",
                        "execution_mode": "automatic",
                        "status": "executing",
                        "execution_started_at": started_at,
                        "execution_result": None,
                        "execution_generation": 1,
                        "retry_count": 0,
                        "max_retries": 2,
                        "escalation_required": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not current_pythonpath
        else str(repo_root) + os.pathsep + current_pythonpath
    )
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from judgment.recovery import recover_interrupted_actions

recovered = recover_interrupted_actions()
assert "free-disk-space" in recovered, recovered
""",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 0, child.stdout + child.stderr

    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in state["actions"]
        if item["action"] == action_name
    )
    assert action["status"] == "failed"
    assert action["execution_result"] == "interrupted-by-restart"

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    events = [
        event for event in audit
        if event.get("event") == "recovery-interrupted"
        and event.get("action") == action_name
    ]
    assert events
    assert events[-1]["status"] == "failed"
    assert events[-1]["result"] == "interrupted-by-restart"
