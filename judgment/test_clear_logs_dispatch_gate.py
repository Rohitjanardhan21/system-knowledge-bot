from unittest.mock import patch

from backend.core.actions import action_executor as executor


def test_manual_clear_logs_is_blocked_before_dispatch():
    with patch.dict(
        executor.EXECUTORS,
        {
            "clear_logs": lambda: (_ for _ in ()).throw(
                AssertionError("clear_logs executor must not run")
            )
        },
    ):
        result = executor.execute_action("clear_logs", source="manual")

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "trusted_log_path_policy_not_implemented"


def test_autonomous_clear_logs_is_blocked_before_dispatch():
    with patch.dict(
        executor.EXECUTORS,
        {
            "clear_logs": lambda: (_ for _ in ()).throw(
                AssertionError("clear_logs executor must not run")
            )
        },
    ):
        result = executor.execute_action("clear_logs", source="auto")

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "action_not_allowed_for_autonomous_execution"


def test_autonomous_allowlist_remains_restricted():
    assert executor.AUTONOMOUS_ALLOWED_ACTIONS == {"clear_temp"}
