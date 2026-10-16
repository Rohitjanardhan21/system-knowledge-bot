import json

from judgment.audit import load_audit
from judgment.lifecycle import retry_failed_action
from state.state_reader import get_action_state


def test_retry_approval_is_recorded_in_isolated_audit(
    isolated_judgment_state,
):
    state_path, _ = isolated_judgment_state
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["actions"][0].update(
        {
            "status": "failed",
            "execution_result": "simulated-execution-failure",
        }
    )
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    action = get_action_state("free-disk-space")
    assert action is not None

    before = load_audit()
    result = retry_failed_action(action)
    after = load_audit()
    new_entries = after[len(before):]

    assert result["status"] == "approved"
    retry_events = [
        entry for entry in new_entries
        if entry.get("event") == "retry-approved"
        and entry.get("action") == "free-disk-space"
    ]
    assert len(retry_events) == 1
    assert retry_events[0]["status"] == "approved"
    assert retry_events[0]["result"] == "retry-approved"
