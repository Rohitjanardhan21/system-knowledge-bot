import json
import os
import subprocess
import sys
from pathlib import Path


def test_audit_crash_before_replace_preserves_authoritative_file(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    audit_path = tmp_path / "state" / "audit.json"
    temp_path = audit_path.with_suffix(".tmp")
    baseline = [
        {"action": "baseline", "result": "baseline-preserved"}
    ]

    audit_path.parent.mkdir(parents=True)
    audit_path.write_text(json.dumps(baseline), encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(repo_root)
        + os.pathsep
        + env.get("PYTHONPATH", "")
    )
    env["PYTHONUTF8"] = "1"

    crash_code = r"""
import json
import os
import sys
from pathlib import Path
import judgment.audit as audit

audit.AUDIT_PATH = Path(sys.argv[1])
audit.AUDIT_TEMP_PATH = audit.AUDIT_PATH.with_suffix(".tmp")
audit.AUDIT_LOCK_PATH = audit.AUDIT_PATH.with_suffix(".lock")

def crash_before_replace(entries):
    with audit.AUDIT_TEMP_PATH.open("w", encoding="utf-8") as stream:
        json.dump(entries, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os._exit(137)

audit._atomic_write_entries = crash_before_replace
audit.record_execution({
    "event": "execution-completed",
    "status": "executed",
    "action": "audit-crash-before-replace",
    "result": "CRASH-BEFORE-REPLACE",
})
raise SystemExit("Expected crash did not occur")
"""

    child = subprocess.run(
        [sys.executable, "-c", crash_code, str(audit_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert child.returncode == 137, (
        f"Expected exit code 137, got {child.returncode}\n"
        f"stdout:\n{child.stdout}\nstderr:\n{child.stderr}"
    )
    assert json.loads(audit_path.read_text(encoding="utf-8")) == baseline
    assert temp_path.exists()

    cleanup_code = r"""
import sys
from pathlib import Path
import judgment.audit as audit

audit.AUDIT_PATH = Path(sys.argv[1])
audit.AUDIT_TEMP_PATH = audit.AUDIT_PATH.with_suffix(".tmp")
audit.AUDIT_LOCK_PATH = audit.AUDIT_PATH.with_suffix(".lock")
audit.cleanup_audit_temp()
print("AUDIT TEMP CLEANUP COMPLETE")
"""

    cleanup = subprocess.run(
        [sys.executable, "-c", cleanup_code, str(audit_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert cleanup.returncode == 0, (
        f"Cleanup failed:\n{cleanup.stdout}\n{cleanup.stderr}"
    )
    assert "AUDIT TEMP CLEANUP COMPLETE" in cleanup.stdout
    assert not temp_path.exists()

    final_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert final_audit == baseline
    assert not any(
        entry.get("result") == "CRASH-BEFORE-REPLACE"
        for entry in final_audit
    )
