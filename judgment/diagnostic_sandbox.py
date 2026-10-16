from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SANDBOX_ENV = "CVIS_DIAGNOSTIC_SANDBOX"


def run_isolated_diagnostic(script_path: str) -> None:
    """Re-run a diagnostic against a disposable copy of the runtime state."""
    if os.environ.get(SANDBOX_ENV) == "1":
        return

    project_root = Path(script_path).resolve().parents[1]

    with tempfile.TemporaryDirectory(prefix="cvis-diagnostic-") as sandbox:
        sandbox_path = Path(sandbox)
        state_source = project_root / "state"
        if state_source.is_dir():
            shutil.copytree(
                state_source,
                sandbox_path / "state",
                ignore=shutil.ignore_patterns("__pycache__"),
            )

        env = os.environ.copy()
        env[SANDBOX_ENV] = "1"
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(project_root)
            if not existing_pythonpath
            else str(project_root) + os.pathsep + existing_pythonpath
        )

        result = subprocess.run(
            [sys.executable, str(Path(script_path).resolve()), *sys.argv[1:]],
            cwd=sandbox_path,
            env=env,
            check=False,
        )

    raise SystemExit(result.returncode)
