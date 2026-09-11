from unittest.mock import MagicMock, patch

import backend.intelligence_pipeline as pipeline


def test_allow_execution_false_never_calls_real_executor():
    fake_decision = {
        "decision": "test remediation",
        "action": "clear_temp",
        "risk_level": "HIGH",
        "confidence": 0.99,
        "auto_execute": True,
        "executable": True,
    }

    fake_executor = MagicMock()
    fake_executor.simulate_learning_step.return_value = {
        "status": "simulated",
        "action": "clear_temp",
        "reward": 1.0,
    }

    with patch.object(pipeline, "load_json", return_value={"metrics": {
        "cpu": 20,
        "memory": 30,
        "disk": 40,
    }}), \
         patch.object(pipeline, "load_nodes", return_value=[]), \
         patch.object(pipeline.learning_engine, "get_baseline", return_value={}), \
         patch.object(pipeline.learning_engine, "detect_anomalies", return_value={}), \
         patch.object(pipeline.learning_engine, "update"), \
         patch.object(pipeline.learning_engine, "detect_patterns", return_value={}), \
         patch.object(pipeline, "aggregate_nodes", return_value=([], [])), \
         patch.object(pipeline, "find_root_cause", return_value=None), \
         patch.object(pipeline, "get_global_top", return_value=None), \
         patch.object(pipeline.decision_engine, "decide", return_value=fake_decision), \
         patch.object(pipeline, "get_timeline", return_value=[]), \
         patch.object(pipeline, "executor", fake_executor):

        result = pipeline.run_intelligence_pipeline(allow_execution=False)

    fake_executor.simulate_learning_step.assert_called_once()
    fake_executor.execute.assert_not_called()

    assert result["execution"] is None
    assert result["decision"]["auto_execute"] is True
    assert result["decision"]["executable"] is True
    assert fake_executor.simulate_learning_step.call_count == 1


def test_allow_execution_false_blocks_even_an_auto_executable_decision():
    fake_executor = MagicMock()
    fake_executor.simulate_learning_step.return_value = {
        "status": "simulated"
    }

    fake_decision = {
        "action": "clear_temp",
        "auto_execute": True,
        "executable": True,
        "risk_level": "HIGH",
        "confidence": 1.0,
        "decision": "test",
    }

    with patch.object(pipeline, "load_json", return_value={"metrics": {}}), \
         patch.object(pipeline, "load_nodes", return_value=[]), \
         patch.object(pipeline.learning_engine, "get_baseline", return_value={}), \
         patch.object(pipeline.learning_engine, "detect_anomalies", return_value={}), \
         patch.object(pipeline.learning_engine, "update"), \
         patch.object(pipeline.learning_engine, "detect_patterns", return_value={}), \
         patch.object(pipeline, "aggregate_nodes", return_value=([], [])), \
         patch.object(pipeline, "find_root_cause", return_value=None), \
         patch.object(pipeline, "get_global_top", return_value=None), \
         patch.object(pipeline.decision_engine, "decide", return_value=fake_decision), \
         patch.object(pipeline, "get_timeline", return_value=[]), \
         patch.object(pipeline, "executor", fake_executor):

        result = pipeline.run_intelligence_pipeline(allow_execution=False)

    assert result["execution"] is None
    fake_executor.execute.assert_not_called()
