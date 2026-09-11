import numpy as np

from backend.dqn_agent import ACTIONS, DQNAgent


def test_dqn_checkpoint_roundtrip(tmp_path, monkeypatch):
    checkpoint = tmp_path / "dqn_checkpoint.pt"
    monkeypatch.setenv("DQN_CHECKPOINT_PATH", str(checkpoint))

    agent = DQNAgent()

    agent.epsilon = 0.123
    agent.step_count = 42

    state = np.zeros(6, dtype=np.float32)
    next_state = np.ones(6, dtype=np.float32)

    agent.remember(
        state,
        ACTIONS[0],
        1.5,
        next_state,
    )

    assert agent.save_checkpoint() is True
    assert checkpoint.exists()

    restored = DQNAgent()

    assert restored.state_dim == agent.state_dim
    assert restored.action_dim == agent.action_dim
    assert restored.epsilon == agent.epsilon
    assert restored.step_count == agent.step_count
    assert len(restored.buffer) == len(agent.buffer)

    for restored_exp, original_exp in zip(restored.buffer, agent.buffer):
        restored_state, restored_action, restored_reward, restored_next_state = restored_exp
        original_state, original_action, original_reward, original_next_state = original_exp

        assert np.array_equal(restored_state, original_state)
        assert restored_action == original_action
        assert restored_reward == original_reward
        assert np.array_equal(restored_next_state, original_next_state)

    for key, value in agent.model.state_dict().items():
        assert np.array_equal(
            value.detach().cpu().numpy(),
            restored.model.state_dict()[key].detach().cpu().numpy(),
        )

    for key, value in agent.target_model.state_dict().items():
        assert np.array_equal(
            value.detach().cpu().numpy(),
            restored.target_model.state_dict()[key].detach().cpu().numpy(),
        )


def test_dqn_rejects_wrong_state_dimension(tmp_path, monkeypatch):
    checkpoint = tmp_path / "dqn_checkpoint.pt"
    monkeypatch.setenv("DQN_CHECKPOINT_PATH", str(checkpoint))

    agent = DQNAgent()
    assert agent.save_checkpoint() is True

    checkpoint_data = __import__("torch").load(
        checkpoint,
        map_location="cpu",
        weights_only=False,
    )
    checkpoint_data["state_dim"] = 999
    __import__("torch").save(checkpoint_data, checkpoint)

    restored = DQNAgent()

    assert restored.step_count == 0


def test_dqn_rejects_wrong_action_dimension(tmp_path, monkeypatch):
    checkpoint = tmp_path / "dqn_checkpoint.pt"
    monkeypatch.setenv("DQN_CHECKPOINT_PATH", str(checkpoint))

    agent = DQNAgent()
    assert agent.save_checkpoint() is True

    checkpoint_data = __import__("torch").load(
        checkpoint,
        map_location="cpu",
        weights_only=False,
    )
    checkpoint_data["action_dim"] = 999
    __import__("torch").save(checkpoint_data, checkpoint)

    restored = DQNAgent()

    assert restored.step_count == 0


def test_dqn_rejects_wrong_action_vocabulary(tmp_path, monkeypatch):
    checkpoint = tmp_path / "dqn_checkpoint.pt"
    monkeypatch.setenv("DQN_CHECKPOINT_PATH", str(checkpoint))

    agent = DQNAgent()
    agent.step_count = 17
    assert agent.save_checkpoint() is True

    checkpoint_data = __import__("torch").load(
        checkpoint,
        map_location="cpu",
        weights_only=False,
    )
    checkpoint_data["actions"] = ["unsafe_action"]
    __import__("torch").save(checkpoint_data, checkpoint)

    restored = DQNAgent()

    assert restored.step_count == 0


def test_dqn_handles_corrupt_checkpoint(tmp_path, monkeypatch):
    checkpoint = tmp_path / "dqn_checkpoint.pt"
    monkeypatch.setenv("DQN_CHECKPOINT_PATH", str(checkpoint))

    checkpoint.write_bytes(b"not-a-valid-pytorch-checkpoint")

    restored = DQNAgent()

    assert restored.step_count == 0
    assert restored.buffer == []
