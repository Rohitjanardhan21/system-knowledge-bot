import json

from judgment.confirmation import approve_action, get_pending_confirmations


def test_confirmation_approval_is_persisted(isolated_judgment_state):
    state_path, _ = isolated_judgment_state
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["actions"][0]["status"] = "requires-confirmation"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    pending = get_pending_confirmations()
    assert any(
        action.get("action") == "free-disk-space"
        and action.get("status") == "requires-confirmation"
        for action in pending
    )

    approved = approve_action("free-disk-space")
    assert approved["status"] == "approved"
    assert not any(
        action.get("action") == "free-disk-space"
        for action in get_pending_confirmations()
    )
