import pytest

from backend.action_executor import ActionExecutor
from backend.core.actions.action_executor import (
    ACTIONS,
    AUTONOMOUS_ALLOWED_ACTIONS,
    execute_action,
)


def test_auto_source_cannot_execute_unallowlisted_action():
    action = next(iter(ACTIONS.keys()))

    assert action not in AUTONOMOUS_ALLOWED_ACTIONS

    result = execute_action(action, source="auto")

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "action_not_allowed_for_autonomous_execution"


def test_unknown_action_is_rejected():
    result = execute_action("__definitely_not_a_real_action__", source="auto")

    assert result["success"] is False
    assert "Unknown action" in result["error"]


def test_simulation_action_vocabulary_is_not_canonical_execution():
    simulation_only = {
        "throttle_background_processes",
        "free_memory_cache",
        "preemptive_cpu_control",
        "kill_high_cpu_process",
        "maintain_state",
    }

    assert simulation_only.isdisjoint(ACTIONS.keys())


def test_autonomous_allowlist_is_explicitly_empty():
    assert not AUTONOMOUS_ALLOWED_ACTIONS


def test_action_executor_requires_explicit_decision_for_execution():
    executor = ActionExecutor.__new__(ActionExecutor)

    assert hasattr(executor, "execute")
    assert callable(executor.execute)
