from backend.action_executor import ActionExecutor


def test_verify_outcome_success():
    executor = ActionExecutor.__new__(ActionExecutor)

    result = executor.verify_outcome(
        "clear_temp",
        {"cpu": 50, "memory": 60, "disk": 90},
        {"cpu": 50, "memory": 60, "disk": 85},
        {"status": "executed"},
    )

    assert result["status"] == "success"
    assert result["verified"] is True
    assert result["metric"] == "disk"
    assert result["delta"] == 5


def test_verify_outcome_partial():
    executor = ActionExecutor.__new__(ActionExecutor)

    result = executor.verify_outcome(
        "clear_temp",
        {"cpu": 50, "memory": 60, "disk": 90},
        {"cpu": 50, "memory": 60, "disk": 90},
        {"status": "executed"},
    )

    assert result["status"] == "partial"
    assert result["verified"] is False
    assert result["delta"] == 0


def test_verify_outcome_failed():
    executor = ActionExecutor.__new__(ActionExecutor)

    result = executor.verify_outcome(
        "clear_temp",
        {"cpu": 50, "memory": 60, "disk": 90},
        {"cpu": 50, "memory": 60, "disk": 95},
        {"status": "executed"},
    )

    assert result["status"] == "failed"
    assert result["verified"] is False
    assert result["delta"] == -5


def test_verify_outcome_unverified_action():
    executor = ActionExecutor.__new__(ActionExecutor)

    result = executor.verify_outcome(
        "kill_high_cpu_process",
        {"cpu": 80, "memory": 60, "disk": 90},
        {"cpu": 70, "memory": 60, "disk": 90},
        {"status": "executed"},
    )

    assert result["status"] == "unverified"
    assert result["verified"] is False
    assert result["reason"] == "action_has_no_verified_metric"


def test_verify_outcome_execution_failure():
    executor = ActionExecutor.__new__(ActionExecutor)

    result = executor.verify_outcome(
        "clear_temp",
        {"cpu": 50, "memory": 60, "disk": 90},
        {"cpu": 50, "memory": 60, "disk": 85},
        {"status": "failed"},
    )

    assert result["status"] == "failed"
    assert result["verified"] is False
    assert result["reason"] == "action_execution_failed"
