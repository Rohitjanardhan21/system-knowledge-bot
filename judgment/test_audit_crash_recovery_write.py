import json
import os
import subprocess
import sys
from pathlib import Path


def test_healthy_audit_writer_cleans_orphan_without_promoting_crash(tmp_path):
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

with audit._audit_lock():
    with audit.AUDIT_TEMP_PATH.open("w", encoding="utf-8") as stream:
        json.dump(
            [{
                "event": "execution-completed",
                "status": "executed",
                "action": "audit-crash-recovery-write",
                "result": "crashed-audit-event",
            }],
            stream,
            indent=2,
        )
        stream.flush()
        os.fsync(stream.fileno())
    os._exit(99)

raise SystemExit("Expected crash did not occur")
"""

    crashed = subprocess.run(
        [sys.executable, "-c", crash_code, str(audit_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert crashed.returncode == 99, (
        f"Expected exit code 99, got {crashed.returncode}\n"
        f"stdout:\n{crashed.stdout}\nstderr:\n{crashed.stderr}"
    )

    assert json.loads(audit_path.read_text(encoding="utf-8")) == baseline
    assert temp_path.exists()

    orphan = json.loads(temp_path.read_text(encoding="utf-8"))
    assert any(
        entry.get("result") == "crashed-audit-event"
        for entry in orphan
    )

    healthy_code = r"""
import sys
from pathlib import Path
import judgment.audit as audit

audit.AUDIT_PATH = Path(sys.argv[1])
audit.AUDIT_TEMP_PATH = audit.AUDIT_PATH.with_suffix(".tmp")
audit.AUDIT_LOCK_PATH = audit.AUDIT_PATH.with_suffix(".lock")

result = audit.record_execution({
    "event": "execution-completed",
    "status": "executed",
    "action": "free-disk-space",
    "result": "post-crash-audit-event",
})
print("HEALTHY WRITER RESULT:", result)
"""

    healthy = subprocess.run(
        [sys.executable, "-c", healthy_code, str(audit_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert healthy.returncode == 0, (
        f"Healthy writer failed:\n{healthy.stdout}\n{healthy.stderr}"
    )

    final_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert baseline[0] in final_audit
    assert not temp_path.exists()

    healthy_matches = [
        entry for entry in final_audit
        if entry.get("result") == "post-crash-audit-event"
        and entry.get("action") == "free-disk-space"
    ]
    crashed_matches = [
        entry for entry in final_audit
        if entry.get("result") == "crashed-audit-event"
    ]

    assert len(healthy_matches) == 1
    assert crashed_matches == []
