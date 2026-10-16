from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from judgment.audit import load_audit, record_execution
from judgment.state_lock import state_lock


STATE_PATH = Path("state") / "latest.json"
STALE_EXECUTION_TIMEOUT = timedelta(minutes=5)


@contextmanager
def interprocess_lock(lock_path):
    with state_lock(Path(lock_path)):
        yield


def _atomic_write_state(state, expected_state_bytes=None):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    temp_path = STATE_PATH.with_suffix(".tmp")

    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())

    # Recovery may have spent time reconciling an older snapshot. Refuse to
    # publish it if another writer replaced the durable state meanwhile.
    if expected_state_bytes is not None:
        try:
            if STATE_PATH.read_bytes() != expected_state_bytes:
                temp_path.unlink(missing_ok=True)
                return False
        except OSError:
            temp_path.unlink(missing_ok=True)
            return False

    os.replace(temp_path, STATE_PATH)
    return True


def _is_valid_recovery_candidate(state):
    if not isinstance(state, dict):
        return False

    actions = state.get("actions")
    if not isinstance(actions, list) or not actions:
        return False

    if any(
        not isinstance(action, dict)
        or not isinstance(action.get("action"), str)
        or not action.get("action")
        or not isinstance(action.get("status"), str)
        for action in actions
    ):
        return False

    return any(
        action.get("status") == "executing"
        or (
            action.get("status") == "failed"
            and action.get("execution_result") == "interrupted-by-restart"
        )
        for action in actions
    )


def _has_recovery_audit(
    audit_entries,
    action_name,
    status="failed",
    result="interrupted-by-restart",
    execution_generation=None,
):
    if not action_name:
        return True

    return any(
        isinstance(event, dict)
        and event.get("event") == "recovery-interrupted"
        and event.get("action") == action_name
        and event.get("status") == status
        and event.get("result") == result
        and (
            execution_generation is None
            or event.get("execution_generation") == execution_generation
        )
        for event in audit_entries
    )


def _is_stale_execution(action, now):
    started_at = action.get("execution_started_at")

    if not isinstance(started_at, str):
        return True

    try:
        started_at = datetime.fromisoformat(started_at)
    except ValueError:
        return True

    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    return now - started_at >= STALE_EXECUTION_TIMEOUT


def _reconcile_executed_audit(state):
    """
    Reconcile executed lifecycle state and completion audits.

    Restore a completion audit from durable state, or promote an
    executing action when its generation has a durable completion audit.
    """

    audit_entries = load_audit()
    reconciled = []

    for action in state.get("actions", []):
        if not isinstance(action, dict):
            continue

        if action.get("status") not in {"executed", "executing"}:
            continue

        action_name = action.get("action")
        result = action.get("execution_result")
        generation = action.get("execution_generation")

        if not action_name or generation is None:
            continue

        completion_event = next((
            event
            for event in audit_entries
            if isinstance(event, dict)
            and event.get("event") == "execution-completed"
            and event.get("action") == action_name
            and event.get("status") == "executed"
            and event.get("execution_generation") == generation
        ), None)

        if action.get("status") == "executing":
            if completion_event is None:
                continue

            action["status"] = "executed"
            action["execution_result"] = completion_event.get("result")
            completed_at = completion_event.get("timestamp")
            action["execution_completed_at"] = (
                completed_at
                if isinstance(completed_at, str)
                else datetime.now(timezone.utc).isoformat()
            )
            reconciled.append(action_name)
            continue

        if completion_event is not None:
            continue

        record_execution([{
            "event": "execution-completed",
            "action": action_name,
            "status": "executed",
            "result": result,
            "execution_generation": generation,
            "recovered": True,
        }])

        reconciled.append(action_name)
        audit_entries = load_audit()

    return reconciled


def _reconcile_failed_state_audit(state):
    """Ensure a failed durable state is reconciled to a single recovery audit."""

    audit_entries = load_audit()
    reconciled = []

    for action in state.get("actions", []):
        if not isinstance(action, dict):
            continue

        if action.get("status") != "failed":
            continue

        action_name = action.get("action")
        if not action_name:
            continue

        action_result = action.get("execution_result")
        if action_result is None:
            action_result = "interrupted-by-restart"

        execution_generation = action.get("execution_generation")
        if _has_recovery_audit(
            audit_entries,
            action_name,
            result=action_result,
            execution_generation=execution_generation,
        ):
            continue

        record_execution([{
            "event": "recovery-interrupted",
            "action": action_name,
            "status": "failed",
            "result": action_result,
            "recovered": True,
            "execution_generation": execution_generation,
        }])
        reconciled.append(action_name)
        audit_entries = load_audit()

    return reconciled


def _reconcile_escalation_resolution_audit(state):
    audit_entries = load_audit()
    reconciled = []

    for action in state.get("actions", []):
        if not isinstance(action, dict):
            continue

        resolution_id = action.get("escalation_resolution_id")
        action_name = action.get("action")
        resolved_by = action.get("escalation_resolved_by")
        if (
            not resolution_id
            or not action_name
            or not isinstance(resolved_by, str)
            or action.get("status") != "approved"
            or action.get("escalation_required") is not False
        ):
            continue

        if any(
            isinstance(event, dict)
            and event.get("event") == "escalation-resolved"
            and event.get("resolution_id") == resolution_id
            for event in audit_entries
        ):
            continue

        record_execution([{
            "event": "escalation-resolved",
            "action": action_name,
            "status": "approved",
            "result": "escalation-resolved",
            "retry_count": action.get("retry_count", 0),
            "max_retries": action.get("max_retries", 2),
            "escalation_required": False,
            "resolution_id": resolution_id,
            "resolved_by": resolved_by,
            "resolved_at": action.get("escalation_resolved_at"),
            "recovered": True,
        }])
        reconciled.append(action_name)
        audit_entries = load_audit()

    return reconciled


def recover_interrupted_actions():
    if not STATE_PATH.exists():
        return []

    recovery_lock_path = STATE_PATH.with_suffix(".recovery.lock")

    with interprocess_lock(recovery_lock_path), state_lock():
        temp_path = STATE_PATH.with_suffix(".tmp")

        try:
            with STATE_PATH.open("r", encoding="utf-8") as f:
                state = json.load(f)
            original_state_bytes = STATE_PATH.read_bytes()
        except (json.JSONDecodeError, OSError):
            try:
                with temp_path.open("r", encoding="utf-8") as f:
                    candidate = json.load(f)
            except (json.JSONDecodeError, OSError):
                return []

            if not _is_valid_recovery_candidate(candidate):
                return []

            try:
                os.replace(temp_path, STATE_PATH)
            except OSError:
                return []

            state = candidate
            original_state_bytes = None

        reconciled = _reconcile_executed_audit(state)
        failed_reconciled = _reconcile_failed_state_audit(state)
        escalation_reconciled = _reconcile_escalation_resolution_audit(state)

        recovered = []
        now = datetime.now(timezone.utc)

        for action in state.get("actions", []):
            if not isinstance(action, dict):
                continue

            action_name = action.get("action")
            execution_generation = action.get("execution_generation")
            if (
                action.get("status") != "executing"
                or not _is_stale_execution(action, now)
            ):
                continue

            action["status"] = "failed"
            action["execution_completed_at"] = now.isoformat()
            action["execution_result"] = "interrupted-by-restart"
            action["recovery_reason"] = (
                "interrupted-by-restart"
            )

            if _has_recovery_audit(
                load_audit(),
                action_name,
                execution_generation=execution_generation,
            ):
                recovered.append(action_name)
                continue

            recovered.append(action_name)

            record_execution([{
                "event": "recovery-interrupted",
                "action": action_name,
                "status": "failed",
                "result": "interrupted-by-restart",
                "execution_generation": execution_generation,
            }])

        if recovered or reconciled or failed_reconciled or escalation_reconciled:
            _atomic_write_state(state, original_state_bytes)

        # Remove an orphaned temporary state left by a previous
        # writer that crashed before os.replace().
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

        return recovered + reconciled + escalation_reconciled


def reconcile_escalation_resolution_audits():
    if not STATE_PATH.exists():
        return []

    recovery_lock_path = STATE_PATH.with_suffix(".recovery.lock")
    with interprocess_lock(recovery_lock_path), state_lock():
        try:
            with STATE_PATH.open("r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError("Unable to read durable action state.") from exc

        return _reconcile_escalation_resolution_audit(state)


if __name__ == "__main__":
    recovered = recover_interrupted_actions()
    print("Recovered:", recovered)
