from __future__ import annotations

import json
from pathlib import Path

import pytest

from judgment import audit, confirmation, lifecycle, recovery, state_lock
from state import state_reader


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    return collection_path.name == "diagnostic_valid_temp_recovery.py."


@pytest.fixture
def isolated_judgment_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"
    lock_path = state_dir / "state.lock"

    state_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "action": "free-disk-space",
                        "priority": "high",
                        "execution_mode": "automatic",
                        "status": "approved",
                        "retry_count": 0,
                        "max_retries": 2,
                        "escalation_required": False,
                        "execution_result": None,
                    },
                    {
                        "action": "reduce-memory-pressure",
                        "priority": "critical",
                        "execution_mode": "automatic",
                        "status": "approved",
                        "retry_count": 0,
                        "max_retries": 2,
                        "escalation_required": False,
                        "execution_result": None,
                    },
                    {
                        "action": "avoid-heavy-workloads",
                        "priority": "high",
                        "execution_mode": "automatic",
                        "status": "approved",
                        "retry_count": 0,
                        "max_retries": 2,
                        "escalation_required": False,
                        "execution_result": None,
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(recovery, "STATE_PATH", state_path)
    monkeypatch.setattr(confirmation, "STATE_PATH", state_path)
    monkeypatch.setattr(state_reader, "STATE_PATH", state_path)

    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", audit_path.with_suffix(".tmp"))
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", audit_path.with_suffix(".lock"))

    original_state_lock = state_lock.state_lock

    def isolated_lock(requested_path=None):
        return original_state_lock(requested_path or lock_path)

    monkeypatch.setattr(lifecycle, "state_lock", isolated_lock)
    monkeypatch.setattr(recovery, "state_lock", isolated_lock)

    return state_path, audit_path
