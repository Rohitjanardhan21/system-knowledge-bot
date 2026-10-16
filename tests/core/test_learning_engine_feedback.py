import pytest

from backend.core.learning_engine import LearningEngine


@pytest.fixture
def engine(monkeypatch):
    instance = LearningEngine.__new__(LearningEngine)
    instance.action_weights = {"monitor": 0.5}
    monkeypatch.setattr(instance, "save_weights", lambda: None)
    return instance


def test_feedback_updates_weight_only_for_verified_success(engine):
    engine.learn_from_feedback(
        "monitor",
        {"status": "success", "verified": True},
    )

    assert engine.action_weights["monitor"] == 0.55


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
