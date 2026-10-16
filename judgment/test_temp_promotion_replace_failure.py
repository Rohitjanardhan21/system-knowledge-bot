import json
import os
import subprocess
import sys
from pathlib import Path


def test_temp_candidate_is_preserved_when_promotion_replace_fails(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    temp_path = state_dir / "latest.tmp"
    audit_path = state_dir / "audit.json"

    corrupt_bytes = b'{"actions": [INVALID'
    candidate = {
        "actions": [
            {
                "action": "free-disk-space",
                "status": "executing",
                "execution_result": None,
                "execution_generation": 1,
            }
        ]
    }
    candidate_bytes = json.dumps(candidate).encode("utf-8")

    state_path.write_bytes(corrupt_bytes)
    temp_path.write_bytes(candidate_bytes)
    audit_path.write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not existing_pythonpath
        else str(repo_root) + os.pathsep + existing_pythonpath
    )
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os
from judgment import recovery

def fail_replace(*args, **kwargs):
    raise OSError("simulated atomic promotion failure")

recovery.os.replace = fail_replace

result = recovery.recover_interrupted_actions()
assert result == [], result
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

    assert child.returncode == 0, child.stdout + child.stderr
    assert state_path.read_bytes() == corrupt_bytes
    assert temp_path.read_bytes() == candidate_bytes
    assert json.loads(audit_path.read_text(encoding="utf-8")) == []
    assert state_path.is_relative_to(tmp_path)
    assert temp_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
