from __future__ import annotations

from judgment.lifecycle import (
    begin_execution,
    complete_execution,
    run_execution_side_effect,
)
from judgment.preconditions import check_preconditions


def execute_plan(plan, dry_run=True, current_facts=None):
    from judgment.action_handlers import execute_action_handler

    results = []

    for item in plan:
        action = item.get("action")
        mode = item.get("execution_mode")
        priority = item.get("priority")

        if mode == "confirmation-required":
            results.append({
                "action": action,
                "priority": priority,
                "execution_mode": mode,
                "status": "blocked",
                "result": "confirmation-required",
            })
            continue

        if mode != "automatic":
            results.append({
                "action": action,
                "priority": priority,
                "execution_mode": mode,
                "status": "rejected",
                "result": "invalid-execution-mode",
            })
            continue

        lifecycle_action = dict(item)
        lifecycle_action["action"] = action

        if lifecycle_action.get("status") is None:
            lifecycle_action["status"] = "approved"

        if lifecycle_action.get("status") == "failed":
            results.append({
                "action": action,
                "priority": priority,
                "execution_mode": mode,
                "status": "blocked",
                "result": "retry-required",
                "reason": (
                    "Failed action requires explicit retry approval "
                    "before execution."
                ),
                "lifecycle_status": "failed",
            })
            continue

        if lifecycle_action.get("status") == "executed":
            results.append({
                "action": action,
                "priority": priority,
                "execution_mode": mode,
                "status": "blocked",
                "result": "already-executed",
                "reason": "Action has already been executed.",
                "lifecycle_status": "executed",
            })
            continue

        if current_facts is not None:
            precondition = check_preconditions(
                lifecycle_action,
                current_facts,
            )

            if not precondition.get("allowed", False):
                results.append({
                    "action": action,
                    "priority": priority,
                    "execution_mode": mode,
                    "status": "blocked",
                    "result": "precondition-failed",
                    "reason": precondition.get(
                        "reason",
                        "Action precondition no longer holds.",
                    ),
                })
                continue

        started = begin_execution(lifecycle_action)

        if started.get("status") != "executing":
            blocked_result = {
                "action": action,
                "priority": priority,
                "execution_mode": mode,
                "status": "blocked",
                "result": started.get("result", "lifecycle-blocked"),
                "reason": started.get("reason", "Lifecycle blocked execution."),
            }
            results.append(blocked_result)
            continue

        # Handler execution MUST be contained by the lifecycle boundary.
        try:
            side_effect = run_execution_side_effect(
                lifecycle_action,
                started["execution_generation"],
                execute_action_handler,
                action,
                dry_run=dry_run,
            )

            if side_effect.get("status") != "allowed":
                results.append({
                    "action": action,
                    "priority": priority,
                    "execution_mode": mode,
                    "status": "blocked",
                    "result": side_effect.get(
                        "result",
                        "execution-not-authorized",
                    ),
                    "reason": side_effect.get(
                        "reason",
                        "Execution side effect was blocked.",
                    ),
                })
                continue

            handler_result = side_effect["value"]

            success = handler_result.get("status") == "simulated"
            handler_result_value = handler_result.get("result")

        except Exception as exc:
            success = False
            handler_result_value = (
                f"{type(exc).__name__}: {exc}"
            )

        completed = complete_execution(
            lifecycle_action,
            success=success,
            result=handler_result_value,
            execution_generation=started["execution_generation"],
        )

        execution_result = {
            "action": action,
            "priority": priority,
            "execution_mode": mode,
            "status": (
                "simulated"
                if success
                else completed.get("status", "failed")
            ),
            "result": (
                "dry-run-success"
                if success
                else completed.get(
                    "result",
                    handler_result_value,
                )
            ),
            "lifecycle_status": completed.get(
                "status",
                "failed",
            ),
            "handler_result": handler_result_value,
            "modified": (
                handler_result.get("modified", False)
                if success
                else False
            ),
        }

        results.append(execution_result)

    return results
