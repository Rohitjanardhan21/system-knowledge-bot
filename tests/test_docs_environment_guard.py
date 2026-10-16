import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("prod", None),
        ("production", None),
        ("dev", "/docs"),
    ],
)
def test_docs_url_matches_environment(mode, expected):
    env = os.environ.copy()
    env.update({
        "ENV": mode,
        "JWT_SECRET": "test-only-jwt-secret-not-for-production",
        "CVIS_API_KEY": "test-only-api-key-not-for-production",
        "CVIS_ADMIN_USER": "test-admin",
        "CVIS_ADMIN_PASS": "test-only-admin-password",
        "GRAFANA_PASS": "test-only-grafana-password",
    })

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from backend.main import app; print(repr(app.docs_url))",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + "\\n" + result.stderr
    assert result.stdout.strip().splitlines()[-1] == repr(expected)
