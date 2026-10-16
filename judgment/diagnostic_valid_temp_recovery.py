from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print("=== VALID TEMP RECOVERY SAFETY TEST ===")

    with tempfile.TemporaryDirectory(prefix="valid-recovery-") as tmp:
        workdir = Path(tmp)
        state_dir = workdir / "state"
        state_dir.mkdir()

        state_path = state_dir / "latest.json"
        temp_path = state_dir / "latest.tmp"

        # A stale executing action simulates a process interrupted by restart.
        started = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        ).isoformat()

        candidate = {
            "actions": [
                {
                    "action": "diagnostic-recovery-check",
                    "status": "executing",
                    "execution_started_at": started,
                    "execution_result": None,
                }
            ]
        }

        state_path.write_text(
            '{"actions": [CORRUPTED}',
            encoding="utf-8",
        )
        temp_path.write_text(
            json.dumps(candidate),
            encoding="utf-8",
        )

        env = os.environ.copy()
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(REPO_ROOT)
            if not existing
            else str(REPO_ROOT) + os.pathsep + existing
        )

        child_code = """
import json
from pathlib import Path
from judgment.recovery import recover_interrupted_actions

state_path = Path("state/latest.json")
temp_path = Path("state/latest.tmp")

recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

assert "diagnostic-recovery-check" in recovered, (
    "Valid interrupted action was not recovered"
)

state = json.loads(state_path.read_text(encoding="utf-8"))
action = next(
    a for a in state["actions"]
    if a["action"] == "diagnostic-recovery-check"
)

assert action["status"] == "failed", action
assert action["execution_result"] == "interrupted-by-restart", action
assert not temp_path.exists(), "Temporary candidate was not cleaned"

print("PASS: valid candidate was promoted")
print("PASS: interrupted action marked failed")
print("PASS: temporary file removed")
"""

        result = subprocess.run(
            [sys.executable, "-c", child_code],
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        print(result.stdout, end="")

        if result.returncode != 0:
            print("FAIL: valid-temp recovery check failed")
            print(result.stderr)
            return 1

        print("PASS: isolated test directory used")
        print("RESULT: PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())