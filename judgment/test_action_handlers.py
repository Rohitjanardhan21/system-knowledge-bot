from judgment.action_handlers import execute_action_handler


def test_action_handlers_are_dry_run_safe():
    actions = [
        "reduce-memory-pressure",
        "free-disk-space",
        "avoid-heavy-workloads",
    ]

    for action in actions:
        result = execute_action_handler(action, dry_run=True)
        assert result["status"] == "simulated"
        assert result["modified"] is False

    unknown = execute_action_handler("unknown-action", dry_run=True)
    assert unknown["status"] == "rejected"
    assert unknown["modified"] is False
