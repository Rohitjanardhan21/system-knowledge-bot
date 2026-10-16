from unittest.mock import patch

import pytest

from backend.action_executor import ActionExecutor


@pytest.fixture
def executor():
    # Bypass initialization so tests cannot start services or background work.
    return ActionExecutor.__new__(ActionExecutor)


def test_public_termination_helper_fails_closed(executor):
    with patch("backend.action_executor.psutil.process_iter") as process_iter:
        result = executor.kill_process_by_name(
            "diagnostic-test-process",
            expected_pid=12345,
            expected_create_time=1000.0,
        )

    assert result["status"] == "blocked_approval"
    assert result["reason"] == "trusted_termination_authority_required"
    process_iter.assert_not_called()


@pytest.mark.parametrize("action", [
    "kill_process",
    "kill_high_cpu_process",
])
def test_dispatcher_requires_termination_authority(executor, action):
    with patch.object(
        executor, "_terminate_process_by_identity"
    ) as terminate:
        result = executor._execute_action(
            action,
            "diagnostic-test-process",
            {
                "target_pid": 12345,
                "target_create_time": 1000.0,
            },
            source="manual",
        )

    assert result["status"] == "blocked_approval"
    assert result["reason"] == "trusted_termination_authority_required"
    terminate.assert_not_called()


def test_private_termination_helper_fails_closed_without_capability(executor):
    with patch("backend.action_executor.psutil.process_iter") as process_iter:
        result = executor._terminate_process_by_identity(
            "diagnostic-test-process",
            expected_pid=12345,
            expected_create_time=1000.0,
        )

    assert result["status"] == "blocked_approval"
    assert result["reason"] == "trusted_termination_authority_required"
    process_iter.assert_not_called()
