import pytest

from backend.core.learning_engine import LearningEngine


@pytest.fixture
def engine(monkeypatch):
    instance = LearningEngine.__new__(LearningEngine)
    instance.action_weights = {"monitor": 0.5}
    instance.action_stats = {}
    monkeypatch.setattr(instance, "save_weights", lambda: None)
    monkeypatch.setattr(instance, "save_stats", lambda: None)
    return instance


def test_feedback_updates_weight_only_for_verified_success(engine):
    engine.learn_from_feedback(
        "monitor",
        {"status": "success", "verified": True},
    )

    assert engine.action_weights["monitor"] == 2 / 3
    assert engine.get_action_stats("monitor")["successes"] == 1


@pytest.mark.parametrize(
    "verification",
    [
        True,
        {"status": "success", "verified": False},
        {"status": "failed", "verified": False},
        {"status": "unverified", "verified": True},
        None,
    ],
)
def test_feedback_without_verified_success_is_rejected(
    engine, verification
):
    with pytest.raises(ValueError, match="Verified successful outcome"):
        engine.learn_from_feedback("monitor", verification)

    assert engine.action_weights["monitor"] == 0.5


@pytest.mark.parametrize("action", ["", "arbitrary-action", None, 123])
def test_feedback_rejects_unsupported_action(engine, action):
    with pytest.raises(ValueError, match="Unsupported feedback action"):
        engine.learn_from_feedback(
            action,
            {"status": "success", "verified": True},
        )

    assert engine.action_weights == {"monitor": 0.5}


def test_trusted_failed_outcome_reduces_weight(engine):
    engine.record_outcome(
        "monitor",
        {"status": "failed", "verified": False},
        trusted=True,
    )

    assert engine.action_weights["monitor"] == 1 / 3
    assert engine.get_action_stats("monitor")["failures"] == 1


def test_workspace_learning_state_isolated(tmp_path, monkeypatch):
    import backend.core.learning_engine as learning_module

    monkeypatch.setattr(
        learning_module,
        "HISTORY_FILE",
        tmp_path / "history" / "learning.json",
    )
    monkeypatch.setattr(
        learning_module,
        "WEIGHTS_FILE",
        tmp_path / "history" / "action_weights.json",
    )
    monkeypatch.setattr(
        learning_module,
        "STATS_FILE",
        tmp_path / "history" / "action_statistics.json",
    )

    first = LearningEngine("workspace-one")
    second = LearningEngine("workspace-two")
    first.record_outcome(
        "monitor",
        {"status": "success", "verified": True},
        trusted=True,
    )

    assert first.get_action_weight("monitor") > 0.5
    assert second.get_action_weight("monitor") == 0.5
