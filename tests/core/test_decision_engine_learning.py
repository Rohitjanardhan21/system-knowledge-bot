from backend import decision_engine


class _LearningStub:
    def __init__(self, weight):
        self.weight = weight

    def get_action_weight(self, action):
        return self.weight

    def get_action_stats(self, action):
        return {
            "successes": 0,
            "partials": 0,
            "failures": 3,
            "samples": 3,
            "weight": self.weight,
            "last_outcome": "failed",
        }


def _decision():
    return decision_engine.compute_decision(
        flat_metrics={
            "cpu_pct": 95,
            "mem_pct": 80,
        },
        forecast={"risk_score": 0.9, "predicted_cpu": 96},
        anomalies=[{"metric": "cpu"}],
        causal={"type": "cpu_overload"},
        temporal={"stability": 0.95, "data_points": 50},
    )


def test_learning_weight_changes_decision_safety_gate(monkeypatch):
    monkeypatch.setattr(decision_engine, "engine", _LearningStub(0.2))

    result = _decision()

    assert result["meta"]["learning_factor"] == 0.2
    assert result["requires_human"] is True
    assert result["auto_execute"] is False


def test_successful_learning_keeps_decision_eligible(monkeypatch):
    monkeypatch.setattr(decision_engine, "engine", _LearningStub(0.8))

    result = _decision()

    assert result["meta"]["learning_factor"] == 0.8
    assert result["requires_human"] is False
    assert result["auto_execute"] is True
