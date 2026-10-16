import json


def test_lifecycle_state_has_free_disk_action(isolated_judgment_state):
    state_path, _ = isolated_judgment_state
    state = json.loads(state_path.read_text(encoding="utf-8"))
    action = next(
        (
            item for item in state.get("actions", [])
            if item.get("action") == "free-disk-space"
        ),
        None,
    )

    assert action is not None
    assert action["status"] == "approved"
