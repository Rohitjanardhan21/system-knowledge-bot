import json

from judgment.confirmation import get_pending_confirmations


def test_pending_confirmations_include_only_actions_awaiting_approval(
    isolated_judgment_state,
):
    state_path, _ = isolated_judgment_state
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for action in state["actions"]:
        if action["action"] == "free-disk-space":
            action["status"] = "requires-confirmation"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    pending = get_pending_confirmations()

    assert len(pending) == 1
    assert pending[0]["action"] == "free-disk-space"
    assert pending[0]["status"] == "requires-confirmation"
