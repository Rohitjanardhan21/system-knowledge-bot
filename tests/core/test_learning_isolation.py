import numpy as np

from backend.action_executor import ActionExecutor
from backend.dqn_agent import DQNAgent


def test_simulation_uses_separate_agent_buffer_and_checkpoint(tmp_path, monkeypatch):
    real_checkpoint = tmp_path / "real.pt"
    monkeypatch.setenv("DQN_CHECKPOINT_PATH", str(real_checkpoint))

    real_agent = DQNAgent()
    executor = ActionExecutor(agent=real_agent)
    simulated_agent = executor.simulation_agent

    assert simulated_agent is not real_agent
    assert simulated_agent.buffer is not real_agent.buffer
    assert simulated_agent.checkpoint_path != real_agent.checkpoint_path

    metrics = {"cpu": 80.0, "memory": 70.0, "disk": 60.0}

    monkeypatch.setattr(
        executor.simulator,
        "apply_action",
        lambda state, action: dict(state),
    )
    monkeypatch.setattr(
        executor.simulator,
        "evaluate_state",
        lambda state, context=None: 0.0,
    )
    monkeypatch.setattr(
        executor.simulator,
        "is_simulation_safe",
        lambda before, after: (True, "safe"),
    )

    result = executor.simulate_learning_step(metrics)

    assert result["status"] == "simulated"
    assert result["trained"] is True
    assert len(simulated_agent.buffer) == 1
    assert len(real_agent.buffer) == 0
    assert not real_checkpoint.exists()
    assert not (tmp_path / "real.pt.simulation").exists()
