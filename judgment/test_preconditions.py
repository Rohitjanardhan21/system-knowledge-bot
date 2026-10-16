from judgment.preconditions import check_preconditions


def test_action_preconditions_follow_current_facts():
    high_memory = {
        "memory": {"utilization": 92},
        "disk": {"utilization": 70},
    }
    low_memory = {
        "memory": {"utilization": 65},
        "disk": {"utilization": 70},
    }
    high_disk = {
        "memory": {"utilization": 70},
        "disk": {"utilization": 93},
    }
    safe_disk = {
        "memory": {"utilization": 70},
        "disk": {"utilization": 70},
    }

    assert check_preconditions(
        {"action": "reduce-memory-pressure"},
        high_memory,
    )["allowed"] is True
    assert check_preconditions(
        {"action": "reduce-memory-pressure"},
        low_memory,
    )["allowed"] is False
    assert check_preconditions(
        {"action": "free-disk-space"},
        high_disk,
    )["allowed"] is True
    assert check_preconditions(
        {"action": "free-disk-space"},
        safe_disk,
    )["allowed"] is False
    assert check_preconditions(
        {"action": "unknown-action"},
        high_disk,
    )["allowed"] is False
