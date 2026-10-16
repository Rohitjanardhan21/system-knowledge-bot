import json
import os
import subprocess
import sys
from pathlib import Path


def test_audit_remains_atomic_when_writer_crashes_before_replace(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    audit_path = state_dir / "audit.json"
    temp_path = state_dir / "audit.tmp"
    lock_path = state_dir / "audit.lock"

    baseline = [{
        "event": "baseline",
        "status": "approved",
        "action": "free-disk-space",
        "result": "baseline-event",
    }]
    audit_path.write_text(json.dumps(baseline), encoding="utf-8")

    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not current_pythonpath
        else str(repo_root) + os.pathsep + current_pythonpath
    )
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json
import os
from pathlib import Path

audit_path = Path("state/audit.json")
temp_path = audit_path.with_suffix(".tmp")

entries = json.loads(audit_path.read_text(encoding="utf-8"))
entries.append({
    "event": "execution-completed",
    "status": "executed",
    "action": "free-disk-space",
    "result": "crash-test-success",
})

with temp_path.open("w", encoding="utf-8") as handle:
    json.dump(entries, handle, indent=2)
    handle.flush()
    os.fsync(handle.fileno())

os._exit(99)
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

    assert child.returncode == 99, child.stdout + child.stderr
    assert json.loads(audit_path.read_text(encoding="utf-8")) == baseline
    assert temp_path.exists()

    temporary = json.loads(temp_path.read_text(encoding="utf-8"))
    assert any(
        event.get("result") == "crash-test-success"
        for event in temporary
    )

    assert audit_path.is_relative_to(tmp_path)
    assert temp_path.is_relative_to(tmp_path)
    assert lock_path.is_relative_to(tmp_path)
