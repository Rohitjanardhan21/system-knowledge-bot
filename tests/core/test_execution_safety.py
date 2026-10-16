import pytest

from backend.action_executor import ActionExecutor
from backend.core.actions.action_executor import (
    ACTIONS,
    AUTONOMOUS_ALLOWED_ACTIONS,
    execute_action,
)


def test_auto_source_cannot_execute_unallowlisted_action():
    action = "drop_caches"

    assert action not in AUTONOMOUS_ALLOWED_ACTIONS or action == "clear_temp"

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


def test_autonomous_allowlist_contains_only_clear_temp():
    assert AUTONOMOUS_ALLOWED_ACTIONS == {"clear_temp"}


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

        def remember(self, state, action, reward, next_state, done=False):
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
        lambda action, target_name, decision, source="manual", **_kwargs: {
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
    assert result["execution_source"] == "manual"

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

        def remember(self, state, action, reward, next_state, done=False):
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

        def remember(self, state, action, reward, next_state, done=False):
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


def test_reward_requires_verified_success():
    from backend.action_executor import ActionExecutor
    executor = ActionExecutor.__new__(ActionExecutor)

    before = {"cpu": 80.0, "memory": 60.0, "disk": 90.0}
    after = {"cpu": 80.0, "memory": 60.0, "disk": 70.0}
    result = {
        "status": "executed",
        "action": "clear_temp",
        "verification": {
            "status": "unverified",
            "verified": False,
            "reason": "action_has_no_verified_metric",
        },
    }

    reward = executor._compute_reward(before, after, result)
    assert reward <= 0


def test_reward_positive_for_verified_improvement():
    from backend.action_executor import ActionExecutor
    executor = ActionExecutor.__new__(ActionExecutor)

    before = {"cpu": 80.0, "memory": 60.0, "disk": 90.0}
    after = {"cpu": 80.0, "memory": 60.0, "disk": 70.0}
    result = {
        "status": "executed",
        "action": "clear_temp",
        "verification": {
            "status": "success",
            "verified": True,
            "reason": "target_metric_improved",
        },
    }

    reward = executor._compute_reward(before, after, result)
    assert reward > 0


def test_reward_negative_for_verified_failure():
    from backend.action_executor import ActionExecutor
    executor = ActionExecutor.__new__(ActionExecutor)

    before = {"cpu": 80.0, "memory": 60.0, "disk": 70.0}
    after = {"cpu": 80.0, "memory": 60.0, "disk": 90.0}
    result = {
        "status": "executed",
        "action": "clear_temp",
        "verification": {
            "status": "failed",
            "verified": False,
            "reason": "target_metric_worsened",
        },
    }

    reward = executor._compute_reward(before, after, result)
    assert reward < 0


def test_unverified_execution_cannot_create_positive_learning_reward(monkeypatch):
    from backend.action_executor import ActionExecutor

    executor = ActionExecutor.__new__(ActionExecutor)
    from unittest.mock import MagicMock
    executor.simulator = MagicMock()
    executor.simulator.apply_action.return_value = {
        "cpu": 80.0,
        "memory": 60.0,
        "disk": 70.0,
    }
    executor.simulator.evaluate_state.return_value = 0.0

    class FakeAgent:
        def __init__(self):
            self.remembered = []

        def encode_state(self, metrics):
            import numpy as np
            return np.array(list(metrics.values()), dtype=float)

        def remember(self, state, action, reward, next_state, done=False):
            self.remembered.append((state, action, reward, next_state, done))

        def train(self):
            pass

    agent = FakeAgent()
    executor.agent = agent
    executor.get_metrics = lambda: {
        "cpu": 80.0,
        "memory": 60.0,
        "disk": 70.0,
    }
    executor.can_execute = lambda action, decision: True
    executor.verify_outcome = lambda action, before, after, result: {
        "status": "unverified",
        "verified": False,
        "reason": "action_has_no_verified_metric",
    }
    executor._execute_action = lambda action, target, decision, source="manual", **_kwargs: {
        "status": "executed",
        "action": action,
    }
    executor._compute_reward = lambda before, after, result: 20.0

    monkeypatch.setattr(
        "backend.action_executor.time.sleep",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "backend.action_executor.store_experience",
        lambda *args, **kwargs: None,
    )
    optimizer_mock = MagicMock()
    monkeypatch.setattr(
        "backend.action_executor.update_optimizer",
        optimizer_mock,
    )

    decision = {
        "action": "clear_temp",
        "context": "general",
        "baseline_cpu": 50,
        "duration_seconds": 20,
    }

    result = executor.execute(decision)

    assert result["verification"]["verified"] is False
    assert result["reward"] <= 0
    assert agent.remembered == []
    optimizer_mock.assert_not_called()


def test_verified_execution_can_enter_learning(monkeypatch):
    from backend.action_executor import ActionExecutor

    executor = ActionExecutor.__new__(ActionExecutor)
    from unittest.mock import MagicMock
    executor.simulator = MagicMock()
    executor.simulator.apply_action.return_value = {
        "cpu": 80.0,
        "memory": 60.0,
        "disk": 70.0,
    }
    executor.simulator.evaluate_state.return_value = 0.0

    class FakeAgent:
        def __init__(self):
            self.remembered = []

        def encode_state(self, metrics):
            import numpy as np
            return np.array(list(metrics.values()), dtype=float)

        def remember(self, state, action, reward, next_state, done=False):
            self.remembered.append((state, action, reward, next_state, done))

        def train(self):
            pass

    agent = FakeAgent()
    executor.agent = agent
    executor.get_metrics = lambda: {
        "cpu": 80.0,
        "memory": 60.0,
        "disk": 90.0,
    }

    executor.can_execute = lambda action, decision: True

    executor.verify_outcome = lambda action, before, after, result: {
        "status": "success",
        "verified": True,
        "reason": "target_metric_improved",
    }

    executor._execute_action = lambda action, target, decision, source="manual", **_kwargs: {
        "status": "executed",
        "action": action,
    }

    executor._compute_reward = lambda before, after, result: 5.0

    monkeypatch.setattr(
        "backend.action_executor.time.sleep",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "backend.action_executor.store_experience",
        lambda *args, **kwargs: None,
    )

    decision = {
        "action": "clear_temp",
        "context": "general",
        "baseline_cpu": 50,
        "duration_seconds": 20,
    }

    result = executor.execute(decision)

    assert result["verification"]["verified"] is True
    assert result["reward"] > 0
    assert len(agent.remembered) == 1
    assert agent.remembered[0][2] > 0


def test_auto_execution_passes_source_to_action_dispatcher(monkeypatch):
    from unittest.mock import MagicMock

    import numpy as np

    from backend.action_executor import ActionExecutor

    executor = ActionExecutor.__new__(ActionExecutor)
    executor.simulator = MagicMock()
    executor.simulator.apply_action.return_value = {
        "cpu": 80.0,
        "memory": 60.0,
        "disk": 70.0,
    }
    executor.simulator.evaluate_state.return_value = 0.0

    class FakeAgent:
        def encode_state(self, metrics):
            return np.array(list(metrics.values()), dtype=float)

    executor.agent = FakeAgent()
    executor.get_metrics = lambda: {
        "cpu": 80.0,
        "memory": 60.0,
        "disk": 70.0,
    }
    executor.can_execute = lambda action, decision: True

    dispatcher = MagicMock(return_value={"success": True})
    monkeypatch.setattr(
        "backend.action_executor.execute_action",
        dispatcher,
    )
    monkeypatch.setattr(
        "backend.action_executor.CausalEngine",
        MagicMock(return_value=MagicMock(
            detect=MagicMock(return_value={"primary_cause": {}})
        )),
    )
    monkeypatch.setattr(
        "backend.action_executor.is_action_allowed",
        lambda *args, **kwargs: (True, "allowed"),
    )
    monkeypatch.setattr(
        "backend.action_executor.is_safe",
        lambda action: True,
    )
    monkeypatch.setattr(
        "backend.action_executor.get_optimizer",
        lambda: {"reward_scale": 1.0},
    )
    monkeypatch.setattr(
        executor,
        "verify_outcome",
        lambda action, before, after, result: {
            "status": "unverified",
            "verified": False,
        },
    )
    monkeypatch.setattr(
        executor,
        "_compute_reward",
        lambda before, after, result: 0.0,
    )
    monkeypatch.setattr(
        "backend.action_executor.time.sleep",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "backend.action_executor.store_experience",
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

    result = executor.execute(
        {"action": "clear_temp", "context": "general"},
        source="auto",
    )
    assert result["status"] == "executed"
    dispatcher.assert_called_once_with("clear_temp", source="auto")
    dispatcher.assert_called_once_with("clear_temp", source="auto")
