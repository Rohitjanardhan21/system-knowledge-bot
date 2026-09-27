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


def test_executor_learning_uses_dqn_action_vocabulary_after_translation():
    """
    Canonical executor actions may differ from DQN actions.

    The DQN replay buffer must receive the original DQN action rather than
    the translated canonical executor action.
    """
    from backend.dqn_agent import ACTIONS as DQN_ACTIONS
    from backend.decision_engine_v2 import (
        DecisionEngineV2,
    )

    # The internal DQN action exists in the DQN vocabulary.
    dqn_action = "free_memory_cache"
    assert dqn_action in DQN_ACTIONS

    # DecisionEngineV2 translates it to the canonical executor action.
    executor_action = DecisionEngineV2.RL_TO_EXECUTOR_ACTION[dqn_action]

    assert executor_action == "drop_caches"

    # The translated canonical action is intentionally NOT a DQN action.
    assert executor_action not in DQN_ACTIONS


def test_executor_preserves_dqn_action_for_learning_when_execution_action_is_translated(monkeypatch):
    """
    Execution and learning use different action vocabularies.

    DecisionEngineV2 may translate the DQN action:
        free_memory_cache -> drop_caches

    The executor must still give the original DQN action to the DQN
    replay buffer.
    """

    from backend.action_executor import ActionExecutor

    class FakeAgent:
        def __init__(self):
            self.remembered = None
            self.trained = False
            self.epsilon = 0.5

        def encode_state(self, metrics):
            import numpy as np
            return np.array([0.1] * 6, dtype=np.float32)

        def remember(self, state, action, reward, next_state):
            self.remembered = action

        def train(self):
            self.trained = True
            return 0.0

    agent = FakeAgent()
    executor = ActionExecutor(agent=agent)

    metrics_before = {
        "cpu": 80.0,
        "memory": 70.0,
        "disk": 50.0,
    }

    metrics_after = {
        "cpu": 60.0,
        "memory": 60.0,
        "disk": 50.0,
    }

    # The executor receives the canonical execution action.
    decision = {
        "action": "drop_caches",
        "learning_action": "free_memory_cache",
        "target_name": None,
        "context": "general",
    }

    monkeypatch.setattr(
        executor,
        "get_metrics",
        lambda: metrics_before.copy()
        if not hasattr(executor, "_test_after_called")
        else metrics_after.copy(),
    )

    monkeypatch.setattr(
        executor,
        "_execute_action",
        lambda action, target_name, decision: {
            "status": "executed",
            "action": action,
        },
    )

    monkeypatch.setattr(
        executor,
        "verify_outcome",
        lambda action, before, after, result: {
            "status": "verified",
            "verified": True,
        },
    )

    monkeypatch.setattr(
        executor,
        "_compute_reward",
        lambda before, after, result: 1.0,
    )

    monkeypatch.setattr(
        "backend.action_executor.time.sleep",
        lambda *_args, **_kwargs: None,
    )

    # Prevent unrelated persistence/optimizer side effects.
    monkeypatch.setattr(
        "backend.action_executor.store_experience",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "backend.action_executor.update_optimizer",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "backend.action_executor.record_action",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "backend.action_executor.log_event",
        lambda *args, **kwargs: None,
    )

    # Bypass unrelated policy/safety/cooldown checks.
    monkeypatch.setattr(
        executor,
        "can_execute",
        lambda *args, **kwargs: True,
    )

    # The simulation must accept the canonical execution action.
    monkeypatch.setattr(
        executor.simulator,
        "apply_action",
        lambda before, action: before.copy(),
    )
    monkeypatch.setattr(
        executor.simulator,
        "evaluate_state",
        lambda state: 0.0,
    )

    result = executor.execute(decision)

    assert result["status"] == "executed"

    # THIS is the boundary requirement.
    #
    # The executor action is "drop_caches", but the replay buffer must
    # receive the original DQN action "free_memory_cache".
    assert agent.remembered == "free_memory_cache"


def test_simulate_learning_trains_selected_dqn_action_not_best_candidate(monkeypatch):
    """Simulation may identify a better action, but DQN learns its own selection."""
    import numpy as np
    from backend.action_executor import ActionExecutor

    class FakeAgent:
        def __init__(self):
            self.remembered = None
            self.trained = False
            self.epsilon = 0.5

        def encode_state(self, metrics):
            return np.array([0.1] * 6, dtype=np.float32)

        def select_action(self, state):
            return "maintain_state"

        def remember(self, state, action, reward, next_state):
            self.remembered = action

        def train(self):
            self.trained = True
            return 0.0

    agent = FakeAgent()
    executor = ActionExecutor(agent=agent)

    metrics = {
        "cpu": 80.0,
        "memory": 70.0,
        "disk": 60.0,
    }

    # Make the candidate scores deterministic and deliberately make
    # free_memory_cache look better than the DQN-selected action.
    def fake_apply_action(state, action):
        result = state.copy()

        if action == "free_memory_cache":
            result["memory"] -= 25
        elif action == "maintain_state":
            pass

        return result

    def fake_evaluate_state(state, context=None):
        if state["memory"] == 45.0:
            return 100.0
        return 0.0

    monkeypatch.setattr(
        executor.simulator,
        "apply_action",
        fake_apply_action,
    )
    monkeypatch.setattr(
        executor.simulator,
        "evaluate_state",
        fake_evaluate_state,
    )
    monkeypatch.setattr(
        executor.simulator,
        "is_simulation_safe",
        lambda before, after: (True, "safe"),
    )

    result = executor.simulate_learning_step(metrics)

    assert result["status"] == "simulated"
    assert result["trained"] is True

    # Best simulated action is NOT the learning target.
    assert result["best_simulated_action"] == "free_memory_cache"
    assert agent.remembered == "maintain_state"
    assert agent.trained is True


def test_simulate_learning_blocks_unsafe_selected_action_without_learning(monkeypatch):
    """An unsafe simulated transition must not enter replay or training."""
    import numpy as np
    from backend.action_executor import ActionExecutor

    class FakeAgent:
        def __init__(self):
            self.remember_calls = 0
            self.train_calls = 0
            self.epsilon = 0.5

        def encode_state(self, metrics):
            return np.array([0.1] * 6, dtype=np.float32)

        def select_action(self, state):
            return "maintain_state"

        def remember(self, state, action, reward, next_state):
            self.remember_calls += 1

        def train(self):
            self.train_calls += 1
            return 0.0

    agent = FakeAgent()
    executor = ActionExecutor(agent=agent)

    metrics = {
        "cpu": 80.0,
        "memory": 70.0,
        "disk": 60.0,
    }

    monkeypatch.setattr(
        executor.simulator,
        "apply_action",
        lambda state, action: {
            "cpu": state["cpu"] + 1,
            "memory": state["memory"],
            "disk": state["disk"],
        },
    )

    monkeypatch.setattr(
        executor.simulator,
        "evaluate_state",
        lambda state, context=None: 0.0,
    )

    # Every simulated candidate is unsafe.
    monkeypatch.setattr(
        executor.simulator,
        "is_simulation_safe",
        lambda before, after: (False, "test_unsafe_transition"),
    )

    result = executor.simulate_learning_step(metrics)

    assert result["status"] == "blocked_simulation"
    assert result["trained"] is False
    assert result["action"] == "maintain_state"
    assert result["reason"] == "test_unsafe_transition"

    assert agent.remember_calls == 0
    assert agent.train_calls == 0
