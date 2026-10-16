import json
import os
import subprocess
import sys
from pathlib import Path


def test_invalid_temp_candidate_is_rejected_without_overwriting_state(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    temp_path = state_dir / "latest.tmp"
    audit_path = state_dir / "audit.json"

    corrupted_state = b'{"actions": [INVALID JSON'
    invalid_temp = b'{"actions": [ALSO INVALID JSON'

    state_path.write_bytes(corrupted_state)
    temp_path.write_bytes(invalid_temp)
    audit_path.write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    )
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from judgment.recovery import recover_interrupted_actions
recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)
assert recovered == []
""",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert state_path.read_bytes() == corrupted_state
    assert temp_path.exists()
    assert temp_path.read_bytes() == invalid_temp
    assert json.loads(audit_path.read_text(encoding="utf-8")) == []
