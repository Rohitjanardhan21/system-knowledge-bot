import json

import judgment.action_handlers as handlers
from judgment.audit import load_audit
from judgment.executor import execute_plan


def test_handler_exception_is_persisted_as_execution_failure(
    isolated_judgment_state,
    monkeypatch,
):
    state_path, _ = isolated_judgment_state
    plan = [
        {
            "action": "free-disk-space",
            "priority": "high",
            "execution_mode": "automatic",
            "status": "approved",
        }
    ]

    def crashing_handler(action, dry_run=True):
        raise RuntimeError("simulated-handler-exception")

    monkeypatch.setattr(handlers, "execute_action_handler", crashing_handler)

    results = execute_plan(
        plan,
        dry_run=True,
        current_facts={
            "disk": {"utilization": 93},
            "memory": {"utilization": 92},
        },
    )

    assert results[0]["status"] == "failed"
    assert "simulated-handler-exception" in results[0]["result"]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        item for item in state["actions"]
        if item["action"] == "free-disk-space"
    )
    assert action["status"] == "failed"
    assert "simulated-handler-exception" in action["execution_result"]

    failure_events = [
        event for event in load_audit()
        if event.get("event") == "execution-failed"
        and event.get("action") == "free-disk-space"
        and event.get("execution_generation")
        == action["execution_generation"]
    ]
    assert len(failure_events) == 1
