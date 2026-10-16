from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


def test_valid_temp_candidate_is_promoted_after_state_corruption(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"
    temp_path = state_dir / "latest.tmp"
    audit_path = state_dir / "audit.json"
    action_name = "free-disk-space"
    started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()

    candidate = {
        "actions": [
            {
                "action": action_name,
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
    state_path.write_text('{"actions": [INVALID', encoding="utf-8")
    temp_path.write_text(json.dumps(candidate), encoding="utf-8")
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

    recovered_state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in recovered_state["actions"]
        if item["action"] == action_name
    )
    assert action["status"] == "failed"
    assert action["execution_result"] == "interrupted-by-restart"
    assert not temp_path.exists()

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert any(
        event.get("event") == "recovery-interrupted"
        and event.get("action") == action_name
        for event in audit
    )
