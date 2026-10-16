from judgment.engine import evaluate


def make_history(memory_values):
    return [
        {
            "timestamp": f"2026-10-02T19:{10+i:02d}:00",
            "cpu": {"usage_percent": 40.0, "cores": 12},
            "memory": {"used_mb": value, "total_mb": 16105.3},
            "disk": {"used_percent": 50.0},
        }
        for i, value in enumerate(memory_values)
    ]


def test_trend_history_influences_judgments():
    base = {
        "cpu": {"usage_percent": 40.0, "cores": 12},
        "memory": {
            "used_mb": 15300.0,
            "total_mb": 16105.3,
        },
        "disk": {"used_percent": 50.0},
        "events": [],
    }

    scenarios = [
        (
            "WORSENING HISTORY",
            [14000, 14200, 14400, 14600, 14800, 15000],
        ),
        (
            "RECOVERING HISTORY",
            [15000, 14800, 14600, 14400, 14200, 14000],
        ),
    ]

    for name, values in scenarios:
        facts = dict(base)
        facts["history"] = make_history(values)

        judgments = evaluate(facts, {})

        assert judgments, f"Expected judgments for {name}"

        history_evidence = [
            evidence
            for judgment in judgments
            for evidence in judgment.evidence
            if evidence.source.startswith("history.")
        ]

        assert history_evidence, (
            f"Expected history-based evidence for {name}"
        )
