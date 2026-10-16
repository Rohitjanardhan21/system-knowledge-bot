from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path

import judgment.lifecycle as lifecycle
import judgment.recovery as recovery


ACTION = "isolated-completion-recovery-race"


def _worker_config(state_path, audit_path, lock_path):
    os.environ["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + os.environ.get("PYTHONPATH", "")
    return {
        "state_path": str(state_path),
        "audit_path": str(audit_path),
        "lock_path": str(lock_path),
    }


def _configure_worker(config):
    import judgment.audit as worker_audit
    import judgment.lifecycle as worker_lifecycle
    import judgment.recovery as worker_recovery
    import judgment.state_lock as lock_module

    state_path = Path(config["state_path"])
    audit_path = Path(config["audit_path"])
    lock_path = Path(config["lock_path"])

    worker_lifecycle.STATE_PATH = state_path
    worker_recovery.STATE_PATH = state_path

    worker_audit.AUDIT_PATH = audit_path
    worker_audit.AUDIT_TEMP_PATH = audit_path.with_suffix(".tmp")
    worker_audit.AUDIT_LOCK_PATH = audit_path.with_suffix(".lock")

    original_lock = lock_module.state_lock

    def isolated_lock(requested_path=None):
        return original_lock(requested_path or lock_path)

    worker_lifecycle.state_lock = isolated_lock
    worker_recovery.state_lock = isolated_lock


def _completion_worker(config, generation, output_path, barrier):
    _configure_worker(config)
    barrier.wait(timeout=15)

    result = lifecycle.complete_execution(
        ACTION,
        success=True,
        result="RECOVERY-RACE-COMPLETION",
        execution_generation=generation,
    )
    Path(output_path).write_text(json.dumps(result), encoding="utf-8")


def _recovery_worker(config, output_path, barrier):
    _configure_worker(config)
    barrier.wait(timeout=15)

    result = recovery.recover_interrupted_actions()
    Path(output_path).write_text(json.dumps(result), encoding="utf-8")


def _read_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def test_ten_process_races_have_one_terminal_winner_and_matching_audit(
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    audit_dir = tmp_path / "audit"
    state_dir.mkdir()
    audit_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = audit_dir / "audit.json"
    lock_path = state_dir / "state.lock"

    # The first generation starts in a durable executing state.
    state = {
        "actions": [
            {
                "action": ACTION,
                "priority": "high",
                "execution_mode": "automatic",
                "status": "executing",
                "retry_count": 0,
                "max_retries": 2,
                "escalation_required": False,
                "execution_result": None,
                "execution_generation": 1,
                "execution_started_at": "2000-01-01T00:00:00+00:00",
            }
        ]
    }
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    audit_path.write_text("[]", encoding="utf-8")

    config = _worker_config(state_path, audit_path, lock_path)
    completion_wins = 0
    recovery_wins = 0

    # Spawn avoids inheriting imported module state from the parent.
    context = multiprocessing.get_context("spawn")

    for round_number in range(1, 11):
        if round_number > 1:
            current = json.loads(state_path.read_text(encoding="utf-8"))
            action = next(a for a in current["actions"] if a["action"] == ACTION)
            action.update(
                {
                    "status": "executing",
                    "execution_result": None,
                    "execution_started_at": "2000-01-01T00:00:00+00:00",
                    "execution_generation": round_number,
                }
            )
            state_path.write_text(json.dumps(current, indent=2), encoding="utf-8")

        generation = round_number
        completion_output = tmp_path / f"completion-{round_number}.json"
        recovery_output = tmp_path / f"recovery-{round_number}.json"
        completion_output.unlink(missing_ok=True)
        recovery_output.unlink(missing_ok=True)

        barrier = context.Barrier(3)
        completion = context.Process(
            target=_completion_worker,
            args=(config, generation, str(completion_output), barrier),
        )
        recover = context.Process(
            target=_recovery_worker,
            args=(config, str(recovery_output), barrier),
        )

        completion.start()
        recover.start()
        barrier.wait(timeout=15)

        completion.join(timeout=30)
        recover.join(timeout=30)

        if completion.is_alive():
            completion.terminate()
            completion.join()
            raise AssertionError(f"Completion worker hung in round {round_number}")
        if recover.is_alive():
            recover.terminate()
            recover.join()
            raise AssertionError(f"Recovery worker hung in round {round_number}")

        assert completion.exitcode == 0, f"completion exit={completion.exitcode}"
        assert recover.exitcode == 0, f"recovery exit={recover.exitcode}"

        completion_result = _read_json(completion_output, {"status": "missing"})
        recovery_result = _read_json(recovery_output, {"status": "missing"})

        durable = json.loads(state_path.read_text(encoding="utf-8"))
        action = next(a for a in durable["actions"] if a["action"] == ACTION)
        status = action.get("status")

        assert action.get("execution_generation") == generation
        assert status in {"executed", "failed"}

        if status == "executed":
            completion_wins += 1
            assert completion_result.get("status") == "executed"
            assert isinstance(recovery_result, list)
            assert ACTION not in recovery_result
        else:
            recovery_wins += 1
            assert action.get("execution_result") == "interrupted-by-restart"
            assert isinstance(recovery_result, list)
            assert ACTION in recovery_result
            assert completion_result.get("status") != "executed"

        entries = _read_json(audit_path, [])
        terminal_events = [
            event for event in entries
            if isinstance(event, dict)
            and event.get("action") == ACTION
            and event.get("execution_generation") == generation
            and event.get("event") in {
                "execution-completed",
                "recovery-interrupted",
            }
        ]

        assert len(terminal_events) == 1, (
            f"round {round_number}: expected one terminal audit event, "
            f"got {terminal_events!r}"
        )
        assert terminal_events[0].get("event") == (
            "execution-completed" if status == "executed"
            else "recovery-interrupted"
        )

    assert completion_wins + recovery_wins == 10

    # Read durable state from a fresh interpreter using the isolated path.
    child_code = """
import json
import sys
from pathlib import Path
state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
target = next(a for a in state["actions"] if a.get("action") == sys.argv[2])
assert target.get("status") in {"executed", "failed"}
assert target.get("execution_generation") == 10
print(target["status"], target["execution_generation"])
"""
    child = subprocess.run(
        [sys.executable, "-c", child_code, str(state_path), ACTION],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip().split()[-1] == "10"

    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)