import json

from judgment.lifecycle import (
    MAX_RETRIES,
    begin_execution,
    complete_execution,
    retry_failed_action,
)
from judgment import recovery


def _load_target():
    state = json.loads(recovery.STATE_PATH.read_text(encoding="utf-8"))
    return next(
        action for action in state["actions"]
        if action.get("action") == "free-disk-space"
    )


def test_retry_budget_escalates_and_blocks_further_retries(
    isolated_judgment_state,
):
    state = json.loads(recovery.STATE_PATH.read_text(encoding="utf-8"))
    target = next(
        action for action in state["actions"]
        if action.get("action") == "free-disk-space"
    )
    target.update(
        {
            "status": "failed",
            "retry_count": 0,
            "max_retries": MAX_RETRIES,
            "escalation_required": False,
            "execution_result": "simulated-failure",
        }
    )
    for key in (
        "execution_started_at",
        "execution_completed_at",
        "recovery_reason",
    ):
        target.pop(key, None)
    recovery.STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    assert target["status"] == "failed"
    assert target["retry_count"] == 0

    for attempt in range(1, MAX_RETRIES + 1):
        retry = retry_failed_action(
            _load_target(),
            current_facts={
                "memory": {"utilization": 92},
                "disk": {"utilization": 93},
            },
        )
        assert retry["status"] == "approved"
        assert retry["retry_count"] == attempt

        start = begin_execution(_load_target())
        assert start["status"] == "executing"

        failure = complete_execution(
            _load_target(),
            success=False,
            result=f"simulated-failure-attempt-{attempt}",
            execution_generation=start["execution_generation"],
        )
        assert failure["status"] == "failed"

        target = _load_target()
        assert target["status"] == "failed"
        assert target["retry_count"] == attempt

    blocked = retry_failed_action(
        _load_target(),
        current_facts={
            "memory": {"utilization": 92},
            "disk": {"utilization": 93},
        },
    )
    assert blocked["status"] == "blocked"
    assert blocked["reason"].startswith(
        f"Retry limit reached ({MAX_RETRIES})"
    )
    assert blocked["retry_count"] == MAX_RETRIES
    assert blocked["max_retries"] == MAX_RETRIES
    assert blocked["escalation_required"] is True

    target = _load_target()
    assert target["status"] == "failed"
    assert target["retry_count"] == MAX_RETRIES
    assert target["escalation_required"] is True
