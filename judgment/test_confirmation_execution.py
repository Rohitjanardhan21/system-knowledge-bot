import json

from judgment.confirmation import approve_action, get_pending_confirmations
from judgment.execution import build_execution_plan
from judgment.executor import execute_plan
from judgment.audit import record_execution


def test_confirmation_executes_only_approved_dry_run(
    isolated_judgment_state,
):
    state_path, _ = isolated_judgment_state
    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = state["actions"][0]
    action.update(
        {
            "status": "requires-confirmation",
            "reason": "Disk utilization exceeds the safe threshold.",
            "validation_reason": "May modify system data.",
        }
    )
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    pending = get_pending_confirmations()
    assert any(
        item.get("action") == "free-disk-space"
        and item.get("status") == "requires-confirmation"
        for item in pending
    )

    approval = approve_action("free-disk-space")
    assert approval["status"] == "approved"
    assert not any(
        item.get("action") == "free-disk-space"
        for item in get_pending_confirmations()
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    approved_actions = [
        item for item in state.get("actions", [])
        if item.get("action") == "free-disk-space"
        and item.get("status") == "approved"
    ]
    plan = build_execution_plan(approved_actions)

    assert any(
        item["action"] == "free-disk-space"
        and item["execution_mode"] == "automatic"
        for item in plan
    )

    results = execute_plan(plan, dry_run=True)
    assert any(
        item["action"] == "free-disk-space"
        and item["status"] == "simulated"
        and item["result"] == "dry-run-success"
        for item in results
    )
    record_execution(results)
