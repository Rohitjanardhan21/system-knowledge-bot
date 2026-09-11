from judgment.engine import evaluate

def test_shadow_mode_normal_is_silent():
    judgments = evaluate(
        facts={"cpu_usage": 22},
        baseline={"cpu_usage": 21}
    )
    assert judgments == []
