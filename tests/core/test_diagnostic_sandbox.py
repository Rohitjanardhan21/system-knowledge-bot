import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_audit_diagnostic_runs_without_mutating_project_state(tmp_path):
    state_files = [
        PROJECT_ROOT / "state" / "latest.json",
        PROJECT_ROOT / "state" / "audit.json",
    ]
    before = {
        path: path.read_bytes() if path.exists() else None
        for path in state_files
    }

    result = subprocess.run(
        [
            sys.executable,
            str(
                PROJECT_ROOT
                / "judgment"
                / "diagnostic_audit_orphaned_temp_cleanup.py"
            ),
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    after = {
        path: path.read_bytes() if path.exists() else None
        for path in state_files
    }
    assert after == before
