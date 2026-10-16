import os
import subprocess
import sys
from pathlib import Path


def test_termination_authority_source_discovery_is_read_only(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    diagnostic = (
        repo_root
        / "judgment"
        / "diagnostic_real_termination_authority_source_discovery.py"
    )

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(repo_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    result = subprocess.run(
        [sys.executable, str(diagnostic)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"Diagnostic failed with exit code {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
    assert "SOURCE LOCATIONS IDENTIFIED." in result.stdout
    assert "NO DESTRUCTIVE CALL WAS EXECUTED." in result.stdout
    assert "RESULT: PASS" in result.stdout
