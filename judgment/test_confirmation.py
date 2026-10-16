import json

from judgment.confirmation import approve_action


def test_approval_fails_closed_when_confirmation_is_not_pending(
    isolated_judgment_state,
):
    state_path, _ = isolated_judgment_state
    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = state["actions"][0]
    action["status"] = "approved"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    result = approve_action("free-disk-space")

    assert result["status"] == "rejected"
    assert result["reason"] == "Action is not awaiting confirmation."
