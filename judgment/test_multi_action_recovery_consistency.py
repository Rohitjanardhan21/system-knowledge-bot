from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


def test_multiple_interrupted_actions_are_recovered_independently(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    expected = {
        "free-disk-space": {
            "retry_count": 0,
            "escalation_required": False,
        },
        "restart-service": {
            "retry_count": 1,
            "escalation_required": False,
        },
        "clear-cache": {
            "retry_count": 2,
            "escalation_required": True,
        },
    }
    started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    state_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "action": name,
                        "priority": "high",
                        "execution_mode": "automatic",
                        "status": "executing",
                        "execution_started_at": started_at,
                        "execution_result": None,
                        "retry_count": values["retry_count"],
                        "max_retries": 2,
                        "escalation_required": values["escalation_required"],
                    }
                    for name, values in expected.items()
                ]
            }
        ),
        encoding="utf-8",
    )

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
required = {"free-disk-space", "restart-service", "clear-cache"}
assert required.issubset(set(recovered)), recovered
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
    for name, values in expected.items():
        action = next(
            item for item in state["actions"]
            if item["action"] == name
        )
        assert action["status"] == "failed"
        assert action["execution_result"] == "interrupted-by-restart"
        assert action["retry_count"] == values["retry_count"]
        assert action["escalation_required"] == values["escalation_required"]

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    recovered_actions = {
        item.get("action")
        for item in audit
        if item.get("event") == "recovery-interrupted"
    }
    assert set(expected).issubset(recovered_actions)
