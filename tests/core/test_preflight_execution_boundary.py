from unittest.mock import MagicMock, patch

from preflight.evaluator import evaluate_preflight
from backend import intelligence_pipeline as pipeline


def _run_with_posture(posture):
    fake_executor = MagicMock()
    fake_executor.simulate_learning_step.return_value = {"status": "simulated"}

    fake_decision = {
        "decision": "test remediation",
        "action": "clear_temp",
        "auto_execute": True,
        "executable": True,
        "risk_level": "HIGH",
        "confidence": 0.99,
    }

    with patch.object(pipeline, "load_json", return_value={
        "metrics": {"cpu": 80, "memory": 30, "disk": 40}
    }), \
    patch.object(pipeline, "load_nodes", return_value=[]), \
    patch.object(pipeline.learning_engine, "get_baseline",
                 return_value={"cpu": {"mean": 60.0, "std": 5.0}}), \
    patch.object(pipeline.learning_engine, "detect_anomalies",
                 return_value={}), \
    patch.object(pipeline.learning_engine, "update"), \
    patch.object(pipeline.learning_engine, "detect_patterns",
                 return_value={}), \
    patch.object(pipeline, "aggregate_nodes", return_value=([], [])), \
    patch.object(pipeline, "find_root_cause", return_value=None), \
    patch.object(pipeline, "get_global_top", return_value=None), \
    patch.object(pipeline.decision_engine, "decide",
                 return_value=fake_decision), \
    patch.object(pipeline, "get_timeline", return_value=[]), \
    patch.object(pipeline, "resolve_posture") as resolve_posture, \
    patch.object(pipeline, "evaluate_preflight") as evaluate_pf, \
    patch.object(pipeline, "executor", fake_executor):

        class Posture:
            pass

        Posture.posture = posture
        resolve_posture.return_value = Posture()

        preflight = evaluate_preflight(posture, [])
        evaluate_pf.return_value = preflight

        result = pipeline.run_intelligence_pipeline(allow_execution=True)

    return result, fake_executor


def test_risky_preflight_blocks_execution():
    result, executor = _run_with_posture("performance-sensitive")

    assert result["preflight"]["decision"] == "risky"
    assert result["execution"] is None
    executor.execute.assert_not_called()


def test_defer_preflight_blocks_execution():
    result, executor = _run_with_posture("capacity-constrained")

    assert result["preflight"]["decision"] == "defer"
    assert result["execution"] is None
    executor.execute.assert_not_called()


def test_safe_preflight_allows_execution_path():
    result, executor = _run_with_posture("idle-capable")

    assert result["preflight"]["decision"] == "safe"
    executor.execute.assert_called_once()
    assert result["execution"] == executor.execute.return_value
