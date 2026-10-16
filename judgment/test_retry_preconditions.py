import json
from contextlib import nullcontext

from judgment import audit, lifecycle


def test_retry_preconditions_are_enforced_in_isolated_state(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    action = {
        "action": "free-disk-space",
        "status": "failed",
        "execution_result": "interrupted-by-restart",
        "retry_count": 0,
        "max_retries": 2,
    }

    state_path.write_text(
        json.dumps({"actions": [action]}, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(audit, "AUDIT_PATH", audit_path)

    # This test targets retry/precondition behavior, not file-lock behavior.
    monkeypatch.setattr(lifecycle, "state_lock", nullcontext)

    target = dict(action)

    healthy_facts = {
        "memory": {"utilization": 60},
        "disk": {"utilization": 70},
    }

    blocked = lifecycle.retry_failed_action(
        target, current_facts=healthy_facts
    )

    assert blocked["status"] == "blocked"
    assert target["status"] == "failed"

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["actions"][0]["status"] == "failed"

    dangerous_facts = {
        "memory": {"utilization": 90},
        "disk": {"utilization": 93},
    }

    approved = lifecycle.retry_failed_action(
        target, current_facts=dangerous_facts
    )

    assert approved["status"] == "approved"
    assert target["status"] == "approved"
    assert target["retry_count"] == 1

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["actions"][0]["status"] == "approved"
    assert persisted["actions"][0]["retry_count"] == 1

    audit_text = audit_path.read_text(encoding="utf-8")
    assert "retry-blocked" in audit_text
    assert "retry-approved" in audit_text
