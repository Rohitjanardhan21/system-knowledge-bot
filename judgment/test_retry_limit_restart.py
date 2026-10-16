from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from judgment.lifecycle import MAX_RETRIES


def test_retry_limit_and_escalation_survive_process_restart(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"
    action_name = "free-disk-space"
    state_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "action": action_name,
                        "status": "failed",
                        "retry_count": MAX_RETRIES,
                        "max_retries": MAX_RETRIES,
                        "escalation_required": True,
                        "execution_result": "simulated-final-failure",
                        "execution_generation": 1,
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
import json
from pathlib import Path
from judgment.lifecycle import retry_failed_action
from judgment.recovery import STATE_PATH

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = next(
    item for item in state["actions"]
    if item["action"] == "free-disk-space"
)
result = retry_failed_action(action)
print(json.dumps({"state": action, "result": result}))
""",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 0, child.stdout + child.stderr

    output = json.loads(child.stdout)
    action = output["state"]
    result = output["result"]
    assert action["status"] == "failed"
    assert action["retry_count"] == MAX_RETRIES
    assert action["max_retries"] == MAX_RETRIES
    assert action["escalation_required"] is True
    assert result["status"] == "blocked"
    assert result["retry_count"] == MAX_RETRIES
    assert result["escalation_required"] is True

    persisted_state = json.loads(state_path.read_text(encoding="utf-8"))
    persisted_action = persisted_state["actions"][0]
    assert persisted_action["status"] == "failed"
    assert persisted_action["retry_count"] == MAX_RETRIES
    assert persisted_action["escalation_required"] is True
