from unittest.mock import patch

import pytest

from backend.core.actions import action_executor as executor


@pytest.mark.parametrize(
    "action_id",
    ["clear_docker_cache", "clear_pip_cache"],
)
def test_manual_cache_cleanup_is_blocked_before_dispatch(action_id):
    def forbidden_executor():
        pytest.fail(f"{action_id} executor must not run without approval")

    with patch.dict(executor.EXECUTORS, {action_id: forbidden_executor}):
        result = executor.execute_action(action_id, source="manual")

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "trusted_approval_not_implemented"
    assert result["action_id"] == action_id


@pytest.mark.parametrize(
    "action_id",
    ["clear_docker_cache", "clear_pip_cache"],
)
def test_autonomous_cache_cleanup_is_blocked_before_dispatch(action_id):
    def forbidden_executor():
        pytest.fail(f"{action_id} executor must not run autonomously")

    with patch.dict(executor.EXECUTORS, {action_id: forbidden_executor}):
        result = executor.execute_action(action_id, source="auto")

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "action_not_allowed_for_autonomous_execution"
    assert result["action_id"] == action_id
