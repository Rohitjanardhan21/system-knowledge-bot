from judgment.rules import cpu_rule

def test_cpu_rule_no_deviation():
    j = cpu_rule(cpu_now=30, cpu_baseline=28)
    assert j is None

def test_cpu_rule_small_deviation():
    j = cpu_rule(cpu_now=45, cpu_baseline=30)
    assert j is not None
    assert j.state == "degraded"
    assert j.urgency == "observe"

def test_cpu_rule_large_deviation():
    j = cpu_rule(cpu_now=80, cpu_baseline=40)
    assert j.state == "constrained"
    assert j.urgency == "act-soon"
