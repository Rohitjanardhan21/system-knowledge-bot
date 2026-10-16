from unittest.mock import MagicMock, patch

from judgment.models import Judgment, Evidence
from backend import intelligence_pipeline as pipeline


def _judgment(state, confidence, scope, urgency, posture, source):
    return Judgment(
        state=state,
        confidence=confidence,
        impact_scope=scope,
        urgency=urgency,
        recommended_posture=posture,
        evidence=[
            Evidence(
                source=source,
                observation=f"{state} condition detected",
                baseline="normal",
                deviation="significant deviation",
            )
        ],
    )


def test_risky_judgment_blocks_autonomous_execution():
    fake_executor = MagicMock()
    fake_executor.simulate_learning_step.return_value = {
        "status": "simulated"
    }

    fake_decision = {
        "action": "clear_temp",
        "auto_execute": True,
        "executable": True,
        "risk_level": "HIGH",
        "confidence": 0.99,
        "decision": "remediate",
    }

    risky = _judgment(
        "risky",
        0.70,
        "system-wide",
        "act-now",
        "stop",
        "system",
    )

    with patch.object(
        pipeline,
        "load_json",
        return_value={
            "metrics": {
                "cpu": 80,
                "memory": 90,
                "disk": 95,
            }
        },
    ), \
    patch.object(pipeline, "load_nodes", return_value=[]), \
    patch.object(
        pipeline.learning_engine,
        "get_baseline",
        return_value={},
    ), \
    patch.object(
        pipeline.learning_engine,
        "detect_anomalies",
        return_value={},
    ), \
    patch.object(
        pipeline.learning_engine,
        "update",
    ), \
    patch.object(
        pipeline.learning_engine,
        "detect_patterns",
        return_value={},
    ), \
    patch.object(
        pipeline,
        "aggregate_nodes",
        return_value=([], []),
    ), \
    patch.object(
        pipeline,
        "find_root_cause",
        return_value=None,
    ), \
    patch.object(
        pipeline,
        "get_global_top",
        return_value=None,
    ), \
    patch.object(
        pipeline.decision_engine,
        "decide",
        return_value=fake_decision,
    ), \
    patch.object(
        pipeline,
        "get_timeline",
        return_value=[],
    ), \
    patch.object(
        pipeline,
        "executor",
        fake_executor,
    ), \
    patch.object(
        pipeline,
        "resolve_posture",
    ) as resolve_posture:

        class Posture:
            posture = "idle-capable"

        resolve_posture.return_value = Posture()

        # The real preflight evaluator must inspect the risky judgment.
        with patch.object(
            pipeline,
            "evaluate",
            return_value=[risky],
        ):
            result = pipeline.run_intelligence_pipeline(
                allow_execution=True
            )

    assert result["preflight"]["decision"] == "defer"
    assert result["execution"] is None
    fake_executor.execute.assert_not_called()


def test_constrained_judgment_blocks_autonomous_execution():
    fake_executor = MagicMock()
    fake_executor.simulate_learning_step.return_value = {
        "status": "simulated"
    }

    fake_decision = {
        "action": "clear_temp",
        "auto_execute": True,
        "executable": True,
        "risk_level": "HIGH",
        "confidence": 0.99,
        "decision": "remediate",
    }

    constrained = _judgment(
        "constrained",
        0.80,
        "system-wide",
        "act-soon",
        "delay",
        "memory",
    )

    with patch.object(
        pipeline,
        "load_json",
        return_value={
            "metrics": {
                "cpu": 80,
                "memory": 90,
                "disk": 95,
            }
        },
    ), \
    patch.object(pipeline, "load_nodes", return_value=[]), \
    patch.object(
        pipeline.learning_engine,
        "get_baseline",
        return_value={},
    ), \
    patch.object(
        pipeline.learning_engine,
        "detect_anomalies",
        return_value={},
    ), \
    patch.object(pipeline.learning_engine, "update"), \
    patch.object(
        pipeline.learning_engine,
        "detect_patterns",
        return_value={},
    ), \
    patch.object(
        pipeline,
        "aggregate_nodes",
        return_value=([], []),
    ), \
    patch.object(
        pipeline,
        "find_root_cause",
        return_value=None,
    ), \
    patch.object(
        pipeline,
        "get_global_top",
        return_value=None,
    ), \
    patch.object(
        pipeline.decision_engine,
        "decide",
        return_value=fake_decision,
    ), \
    patch.object(
        pipeline,
        "get_timeline",
        return_value=[],
    ), \
    patch.object(
        pipeline,
        "executor",
        fake_executor,
    ), \
    patch.object(
        pipeline,
        "evaluate",
        return_value=[constrained],
    ):

        result = pipeline.run_intelligence_pipeline(
            allow_execution=True
        )

    assert result["preflight"]["decision"] == "defer"
    assert result["execution"] is None
    fake_executor.execute.assert_not_called()
