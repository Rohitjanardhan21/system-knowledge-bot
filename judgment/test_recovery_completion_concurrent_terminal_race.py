from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import judgment.audit as audit
import judgment.lifecycle as lifecycle
import judgment.recovery as recovery
import judgment.state_lock as state_lock_module


def test_completion_and_recovery_have_one_terminal_winner(
    tmp_path: Path,
    monkeypatch,
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"
    lock_path = state_dir / "state.lock"

    action_name = "isolated-recovery-completion-race"
    generation = 1

    initial_state = {
        "actions": [
            {
                "action": action_name,
                "priority": "high",
                "execution_mode": "automatic",
                "status": "executing",
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
                "execution_result": None,
                "execution_generation": generation,
                "execution_started_at": "2000-01-01T00:00:00+00:00",
            }
        ]
    }
    state_path.write_text(
        json.dumps(initial_state, indent=2),
        encoding="utf-8",
    )

    # Redirect all durable state and audit files into this test's directory.
    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(recovery, "STATE_PATH", state_path)
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit, "AUDIT_TEMP_PATH", audit_path.with_suffix(".tmp"))
    monkeypatch.setattr(audit, "AUDIT_LOCK_PATH", audit_path.with_suffix(".lock"))

    # state_lock's default path was bound when its function was defined.
    # Supply an explicit temporary lock path for calls from both modules.
    original_state_lock = state_lock_module.state_lock

    def isolated_state_lock(requested_path=None):
        return original_state_lock(requested_path or lock_path)

    monkeypatch.setattr(lifecycle, "state_lock", isolated_state_lock)
    monkeypatch.setattr(recovery, "state_lock", isolated_state_lock)

    barrier = threading.Barrier(3)

    def complete():
        barrier.wait(timeout=10)
        return lifecycle.complete_execution(
            action_name,
            success=True,
            result="race-completion-winner",
            execution_generation=generation,
        )

    def recover():
        barrier.wait(timeout=10)
        return recovery.recover_interrupted_actions()

    with ThreadPoolExecutor(max_workers=2) as pool:
        completion_future = pool.submit(complete)
        recovery_future = pool.submit(recover)

        # Release both workers as close together as possible.
        barrier.wait(timeout=10)

        completion_result = completion_future.result(timeout=15)
        recovery_result = recovery_future.result(timeout=15)

    assert isinstance(completion_result, dict)
    assert isinstance(recovery_result, list)

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in final_state["actions"]
        if item["action"] == action_name
    )

    assert action["execution_generation"] == generation
    assert action["status"] in {"executed", "failed"}

    entries = audit.load_audit()
    terminal_events = [
        event for event in entries
        if isinstance(event, dict)
        and event.get("action") == action_name
        and event.get("execution_generation") == generation
        and event.get("event") in {
            "execution-completed",
            "recovery-interrupted",
        }
    ]

    # Exactly one operation must own the terminal transition.
    assert len(terminal_events) == 1

    if action["status"] == "executed":
        assert terminal_events[0]["event"] == "execution-completed"
        assert terminal_events[0].get("status") == "executed"
    else:
        assert terminal_events[0]["event"] == "recovery-interrupted"
        assert terminal_events[0].get("status") == "failed"
        assert action["execution_result"] == "interrupted-by-restart"

    # Prove the test used only its isolated durable files.
    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)