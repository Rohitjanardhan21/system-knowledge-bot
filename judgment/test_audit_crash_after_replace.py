import json
import os
import subprocess
import sys
from pathlib import Path


def test_audit_crash_after_replace_preserves_exactly_one_event(tmp_path):
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

def crash_after_replace(entries):
    with audit.AUDIT_TEMP_PATH.open("w", encoding="utf-8") as stream:
        json.dump(entries, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(audit.AUDIT_TEMP_PATH, audit.AUDIT_PATH)
    os._exit(137)

audit._atomic_write_entries = crash_after_replace
audit.record_execution({
    "event": "execution-completed",
    "status": "executed",
    "action": "audit-crash-after-replace",
    "result": "CRASH-AFTER-REPLACE",
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

    durable = json.loads(audit_path.read_text(encoding="utf-8"))
    matches = [
        entry for entry in durable
        if entry.get("action") == "audit-crash-after-replace"
        and entry.get("event") == "execution-completed"
        and entry.get("result") == "CRASH-AFTER-REPLACE"
    ]

    assert len(matches) == 1
    assert durable[0] == baseline[0]
    assert not temp_path.exists()

    read_code = r"""
import json
import sys
from pathlib import Path
import judgment.audit as audit

audit.AUDIT_PATH = Path(sys.argv[1])
audit.AUDIT_TEMP_PATH = audit.AUDIT_PATH.with_suffix(".tmp")
audit.AUDIT_LOCK_PATH = audit.AUDIT_PATH.with_suffix(".lock")
print(json.dumps(audit.load_audit()))
"""

    fresh = subprocess.run(
        [sys.executable, "-c", read_code, str(audit_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert fresh.returncode == 0, (
        f"Fresh read failed:\n{fresh.stdout}\n{fresh.stderr}"
    )

    fresh_audit = json.loads(fresh.stdout.strip())
    fresh_matches = [
        entry for entry in fresh_audit
        if entry.get("action") == "audit-crash-after-replace"
        and entry.get("event") == "execution-completed"
        and entry.get("result") == "CRASH-AFTER-REPLACE"
    ]

    assert len(fresh_matches) == 1
    assert fresh_audit == durable
    assert not temp_path.exists()
