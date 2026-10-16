from judgment.trend import analyze_history


def test_analyze_history_classifies_cpu_memory_and_disk():
    history = [
        {
            "cpu": {"usage_percent": cpu},
            "memory": {"used_mb": memory},
            "disk": {"used_percent": disk},
        }
        for cpu, memory, disk in [
            (20, 1500, 30),
            (22, 1400, 32),
            (24, 1300, 34),
            (26, 1200, 36),
        ]
    ]

    result = analyze_history(history)

    assert set(result) == {"cpu", "memory", "disk"}
    assert result["cpu"]["trend"] == "worsening"
    assert result["memory"]["trend"] == "recovering"
    assert result["disk"]["trend"] == "worsening"


def test_classification_handles_insufficient_data():
    history = [
        {
            "cpu": {"usage_percent": 20},
            "memory": {"used_mb": 1000},
            "disk": {"used_percent": 30},
        }
    ]

    result = analyze_history(history)

    assert result["cpu"]["trend"] == "insufficient-data"
    assert result["memory"]["trend"] == "insufficient-data"
    assert result["disk"]["trend"] == "insufficient-data"


def test_classification_handles_persistent_and_volatile_trends():
    persistent_history = [
        {"cpu": {"usage_percent": value}}
        for value in (20, 20.2, 20.1, 20.3)
    ]
    volatile_history = [
        {"cpu": {"usage_percent": value}}
        for value in (20, 22, 20, 22)
    ]

    assert analyze_history(persistent_history)["cpu"]["trend"] == "persistent"
    assert analyze_history(volatile_history)["cpu"]["trend"] == "volatile"
