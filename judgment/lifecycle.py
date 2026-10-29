from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import time
from judgment.audit import record_execution
from judgment.state_lock import state_lock

STATE_PATH = Path("state") / "latest.json"


TERMINAL_STATUSES = {"executed", "failed", "rejected"}
MAX_RETRIES = 2


def _resolve_action_record(action):
    if isinstance(action, dict):
        return action

    name = str(action)

    if not STATE_PATH.exists():
        return {"action": name, "status": "approved"}

    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"action": name, "status": "approved"}

    for stored in state.get("actions", []):
        if isinstance(stored, dict) and stored.get("action") == name:
            return stored

    return {"action": name, "status": "approved"}


def _get_retry_count(action):
    retry_count = action.get("retry_count", 0)
    if not isinstance(retry_count, int) or retry_count < 0:
        return 0
    return retry_count


def _get_max_retries(action):
    max_retries = action.get("max_retries", MAX_RETRIES)
    if (
        not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or max_retries < 0
    ):
        return MAX_RETRIES
    return max_retries


def _get_execution_generation(action):
    generation = action.get("execution_generation", 0)
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 0
    ):
        return 0
    return generation


def _retry_budget_exhausted(action, retry_count):
    max_retries = _get_max_retries(action)
    return (
        action.get("escalation_required") is True
        or (
            action.get("status") == "failed"
            and retry_count >= max_retries
        )
    )


def _persist_action(action):
    if not STATE_PATH.exists():
        raise FileNotFoundError(f"Action state does not exist: {STATE_PATH}")

    with STATE_PATH.open("r", encoding="utf-8") as f:
        state = json.load(f)

    actions = state.get("actions", [])
    target = action.get("action")
    for stored in actions:
        if isinstance(stored, dict) and stored.get("action") == target:
            stored.clear()
            stored.update(action)
            break
    else:
        raise KeyError(f"Action is missing from durable state: {target}")

    temp_path = STATE_PATH.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())

    for attempt in range(6):
        try:
            os.replace(temp_path, STATE_PATH)
            break
        except PermissionError:
            if os.name != "nt" or attempt == 5 or not temp_path.exists():
                raise
            time.sleep(min(0.01 * (2**attempt), 0.1))


def begin_execution(action):
    action = _resolve_action_record(action)
    action_name = action.get("action")

    with state_lock():
        # Re-read durable state while holding the lock.
        persisted_action = None

        if STATE_PATH.exists():
            try:
                with STATE_PATH.open("r", encoding="utf-8") as f:
                    state = json.load(f)

                for stored in state.get("actions", []):
                    if (
                        isinstance(stored, dict)
                        and stored.get("action") == action.get("action")
                    ):
                        persisted_action = stored
                        break

            except (json.JSONDecodeError, OSError):
                persisted_action = None

        effective_status = (
            persisted_action.get("status")
            if persisted_action is not None
            else action.get("status")
        )
        effective_action = persisted_action or action
        retry_count = _get_retry_count(effective_action)
        max_retries = _get_max_retries(effective_action)

        if effective_action is not action:
            action.clear()
            action.update(effective_action)
            effective_action = action

        if effective_status == "executed":
            return {
                "status": "blocked",
                "result": "already-executed",
                "reason": "Action has already been executed.",
            }

        if effective_status == "executing":
            return {
                "status": "blocked",
                "result": "already-executing",
                "reason": "Action is already executing.",
            }

        if _retry_budget_exhausted(effective_action, retry_count):
            effective_action["retry_count"] = retry_count
            effective_action["max_retries"] = max_retries
            effective_action["escalation_required"] = True
            _persist_action(effective_action)
            return {
                "status": "blocked",
                "result": "retry-limit-reached",
                "reason": (
                    f"Retry limit reached ({max_retries}). "
                    "Further automatic execution is blocked."
                ),
                "retry_count": retry_count,
                "max_retries": max_retries,
                "escalation_required": True,
            }

        if effective_status != "approved":
            return {
                "status": "blocked",
                "result": (
                    "retry-required"
                    if effective_status == "failed"
                    else "lifecycle-blocked"
                ),
                "reason": (
                    f"Action cannot begin execution from status "
                    f"'{effective_status}'."
                ),
            }

        execution_generation = (
            _get_execution_generation(effective_action) + 1
        )
        effective_action["status"] = "executing"
        effective_action["execution_generation"] = execution_generation
        effective_action["execution_started_at"] = (
            datetime.now(timezone.utc).isoformat()
        )

        _persist_action(effective_action)

        record_execution([{
            "event": "execution-started",
            "action": action_name,
            "status": "executing",
            "result": "execution-started",
        }])

        return {
            "status": "executing",
            "action": action_name,
            "execution_generation": execution_generation,
        }


def run_execution_side_effect(
    action,
    execution_generation,
    side_effect,
    *args,
    **kwargs,
):
    action = _resolve_action_record(action)
    action_name = action.get("action")

    with state_lock():
        effective_action = action

        if STATE_PATH.exists():
            try:
                with STATE_PATH.open("r", encoding="utf-8") as f:
                    state = json.load(f)

                for stored in state.get("actions", []):
                    if (
                        isinstance(stored, dict)
                        and stored.get("action") == action_name
                    ):
                        effective_action = stored
                        break

            except (json.JSONDecodeError, OSError):
                pass

        current_generation = _get_execution_generation(effective_action)
        if (
            effective_action.get("status") != "executing"
            or execution_generation != current_generation
        ):
            return {
                "status": "blocked",
                "result": "stale-execution-generation",
                "reason": (
                    "Worker execution generation is not active; "
                    "side effect was rejected."
                ),
                "action": action_name,
                "execution_generation": execution_generation,
                "current_execution_generation": current_generation,
            }

        return {
            "status": "allowed",
            "action": action_name,
            "execution_generation": current_generation,
            "value": side_effect(*args, **kwargs),
        }


def complete_execution(
    action,
    success=True,
    result=None,
    execution_generation=None,
):
    action = _resolve_action_record(action)
    action_name = action.get("action")
    requested_generation = (
        _get_execution_generation(action)
        if execution_generation is None
        else execution_generation
    )

    with state_lock():
        effective_action = action

        if STATE_PATH.exists():
            try:
                with STATE_PATH.open("r", encoding="utf-8") as f:
                    state = json.load(f)

                for stored in state.get("actions", []):
                    if (
                        isinstance(stored, dict)
                        and stored.get("action") == action_name
                    ):
                        effective_action = stored
                        break

            except (json.JSONDecodeError, OSError):
                pass

        current_generation = _get_execution_generation(effective_action)

        if requested_generation != current_generation:
            return {
                "status": "blocked",
                "result": "stale-execution-generation",
                "reason": (
                    "Worker execution generation is stale; "
                    "completion was rejected."
                ),
                "action": action_name,
                "execution_generation": requested_generation,
                "current_execution_generation": current_generation,
            }

        if effective_action is not action:
            action.clear()
            action.update(effective_action)
            effective_action = action

        if effective_action.get("status") != "executing":
            return {
                "status": "blocked",
                "reason": "Action is not currently executing.",
            }

        effective_action["status"] = "executed" if success else "failed"
        effective_action["execution_completed_at"] = (
            datetime.now(timezone.utc).isoformat()
        )
        effective_action["execution_result"] = result or (
            "success" if success else "execution-failed"
        )

        _persist_action(effective_action)
        record_execution([{
            "event": "execution-completed" if success else "execution-failed",
            "action": action_name,
            "status": effective_action["status"],
            "result": effective_action["execution_result"],
            "execution_generation": current_generation,
        }])

        return {
            "status": effective_action["status"],
            "action": action_name,
            "result": effective_action["execution_result"],
        }


def retry_failed_action(action, current_facts=None):
    action = _resolve_action_record(action)
    action_name = action.get("action")

    with state_lock():
        effective_action = action

        if STATE_PATH.exists():
            try:
                with STATE_PATH.open("r", encoding="utf-8") as f:
                    state = json.load(f)

                for stored in state.get("actions", []):
                    if (
                        isinstance(stored, dict)
                        and stored.get("action") == action_name
                    ):
                        effective_action = stored
                        break

            except (json.JSONDecodeError, OSError):
                pass

        if effective_action is not action:
            action.clear()
            action.update(effective_action)
            effective_action = action

        status = effective_action.get("status")
        retry_count = _get_retry_count(effective_action)
        max_retries = _get_max_retries(effective_action)

        if _retry_budget_exhausted(effective_action, retry_count):
            effective_action["retry_count"] = retry_count
            effective_action["max_retries"] = max_retries
            effective_action["escalation_required"] = True

            _persist_action(effective_action)

            record_execution([{
                "event": "retry-blocked",
                "action": action_name,
                "status": "blocked",
                "result": "retry-limit-reached",
            }])

            return {
                "status": "blocked",
                "action": action_name,
                "reason": (
                    f"Retry limit reached ({max_retries}). "
                    "Further automatic retry is blocked."
                ),
                "retry_count": retry_count,
                "max_retries": max_retries,
                "escalation_required": True,
            }

        if status != "failed":
            record_execution([{
                "event": "retry-blocked",
                "action": action_name,
                "status": "blocked",
                "result": "retry-not-available",
            }])

            return {
                "status": "blocked",
                "reason": (
                    f"Only failed actions can be retried; "
                    f"current status is '{status}'."
                ),
            }

        if current_facts is not None:
            from judgment.preconditions import check_preconditions

            precondition = check_preconditions(
                effective_action,
                current_facts,
            )

            if not precondition.get("allowed", False):
                record_execution([{
                    "event": "retry-blocked",
                    "action": action_name,
                    "status": "blocked",
                    "result": "precondition-failed",
                }])

                return {
                    "status": "blocked",
                    "reason": (
                        "Retry blocked: current precondition no longer holds. "
                        + precondition.get(
                            "reason",
                            "Action precondition failed.",
                        )
                    ),
                }

        retry_count += 1

        effective_action["retry_count"] = retry_count
        effective_action["max_retries"] = max_retries
        effective_action["escalation_required"] = False
        effective_action["status"] = "approved"

        if effective_action.get("execution_mode") is None:
            effective_action["execution_mode"] = "automatic"

        effective_action.pop("execution_started_at", None)
        effective_action.pop("execution_completed_at", None)
        effective_action.pop("execution_result", None)
        effective_action.pop("recovery_reason", None)

        _persist_action(effective_action)

        record_execution([{
            "event": "retry-approved",
            "action": action_name,
            "status": "approved",
            "result": "retry-approved",
            "retry_count": retry_count,
            "max_retries": max_retries,
        }])

        return {
            "status": "approved",
            "action": action_name,
            "reason": "Failed action explicitly approved for retry.",
            "retry_count": retry_count,
            "max_retries": max_retries,
            "escalation_required": False,
        }


def resolve_escalation(action, *, principal):
    if (
        not isinstance(principal, dict)
        or principal.get("scope") != "admin"
        or principal.get("_source") not in {"api_key", "jwt"}
    ):
        raise PermissionError("An authenticated admin principal is required.")

    resolved_by = principal.get("sub") or principal.get("name")
    if not isinstance(resolved_by, str) or not resolved_by.strip():
        raise PermissionError("The admin principal has no auditable identity.")

    action = _resolve_action_record(action)
    action_name = action.get("action")

    with state_lock():
        effective_action = dict(action)

        if STATE_PATH.exists():
            with STATE_PATH.open("r", encoding="utf-8") as f:
                state = json.load(f)

            for stored in state.get("actions", []):
                if (
                    isinstance(stored, dict)
                    and stored.get("action") == action_name
                ):
                    effective_action = dict(stored)
                    break

        retry_count = _get_retry_count(effective_action)
        max_retries = _get_max_retries(effective_action)

        if not effective_action.get("escalation_required"):
            return {
                "status": "blocked",
                "action": action_name,
                "reason": "Action is not currently escalated.",
                "retry_count": retry_count,
                "escalation_required": False,
            }

        effective_action["status"] = "approved"
        effective_action["retry_count"] = 0
        effective_action["max_retries"] = max_retries
        effective_action["escalation_required"] = False
        resolution_id = secrets.token_urlsafe(24)
        resolved_at = datetime.now(timezone.utc).isoformat()
        effective_action["escalation_resolution_id"] = resolution_id
        effective_action["escalation_resolved_by"] = resolved_by
        effective_action["escalation_resolved_at"] = resolved_at
        effective_action["execution_mode"] = effective_action.get(
            "execution_mode",
            "automatic",
        )

        effective_action.pop("execution_started_at", None)
        effective_action.pop("execution_completed_at", None)
        effective_action.pop("execution_result", None)
        effective_action.pop("recovery_reason", None)

        _persist_action(effective_action)

        record_execution([{
            "event": "escalation-resolved",
            "action": action_name,
            "status": "approved",
            "result": "escalation-resolved",
            "retry_count": 0,
            "max_retries": max_retries,
            "escalation_required": False,
            "resolution_id": resolution_id,
            "resolved_by": resolved_by,
            "resolved_at": resolved_at,
        }])

        return {
            "status": "approved",
            "action": action.get("action"),
            "reason": "Escalation explicitly resolved; execution re-authorized.",
            "retry_count": 0,
            "max_retries": max_retries,
            "escalation_required": False,
        }


def can_execute(action):
    retry_count = _get_retry_count(action)
    return (
        action.get("status") == "approved"
        and not _retry_budget_exhausted(action, retry_count)
    )
