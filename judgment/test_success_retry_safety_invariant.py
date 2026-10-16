import json
import os
import subprocess
import sys
from pathlib import Path


def test_successful_action_cannot_be_retried(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    original_retry_count = 1
    state_path.write_text(
        json.dumps({
            "actions": [{
                "action": "free-disk-space",
                "priority": "high",
                "execution_mode": "automatic",
                "status": "executed",
                "retry_count": original_retry_count,
                "max_retries": 2,
                "escalation_required": False,
                "execution_result": "successful-terminal-state",
            }]
        }, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    script = r'''
import json
from pathlib import Path
from judgment.retry import retry_failed_action

state_path = Path("state/latest.json")
before = json.loads(state_path.read_text(encoding="utf-8"))
before_action = next(
    a for a in before["actions"]
    if a.get("action") == "free-disk-space"
)

result = retry_failed_action("free-disk-space")
assert result["status"] == "blocked", result

after = json.loads(state_path.read_text(encoding="utf-8"))
after_action = next(
    a for a in after["actions"]
    if a.get("action") == "free-disk-space"
)

assert after_action["status"] == "executed"
assert after_action["execution_result"] == "successful-terminal-state"
assert after_action["retry_count"] == before_action["retry_count"]

print("RESULT: PASS")
'''

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(repo_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"Retry invariant failed with exit code {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
    assert "RESULT: PASS" in result.stdout

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    final_action = final_state["actions"][0]
    assert final_action["status"] == "executed"
    assert final_action["execution_result"] == "successful-terminal-state"
    assert final_action["retry_count"] == original_retry_count
