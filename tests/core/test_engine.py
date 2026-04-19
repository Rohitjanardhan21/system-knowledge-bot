from judgment.engine import evaluate

def test_engine_returns_list():
    snapshot = {"cpu_usage": 50}
    baseline = {"cpu_usage": 30}

    judgments = evaluate(snapshot, baseline)
    assert isinstance(judgments, list)

def test_engine_empty_when_normal():
    snapshot = {"cpu_usage": 25}
    baseline = {"cpu_usage": 23}

    judgments = evaluate(snapshot, baseline)
    assert judgments == []
