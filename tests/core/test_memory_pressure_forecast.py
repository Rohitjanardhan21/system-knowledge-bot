from collections import deque

import backend.main as main


def _memory_samples(values: list[float], start: float = 1500.0) -> deque:
    return deque(
        {"timestamp": start + index * 50, "memory": value}
        for index, value in enumerate(values)
    )


def test_memory_forecast_reports_normal_when_usage_is_stable(monkeypatch):
    now = 1800.0
    monkeypatch.setattr(
        main,
        "_memory_usage_history",
        _memory_samples([50, 50, 50, 50, 50, 50], start=1550),
    )
    monkeypatch.setattr(main, "_process_trend_history", deque())

    forecast = main._memory_pressure_forecast(now)

    assert forecast["status"] == "normal"
    assert forecast["current_percent"] == 50.0
    assert forecast["minutes_to_90_percent"] is None


def test_memory_forecast_warns_when_usage_is_rising(monkeypatch):
    now = 1800.0
    monkeypatch.setattr(
        main,
        "_memory_usage_history",
        _memory_samples([60, 60, 61, 70, 75, 80], start=1500),
    )
    monkeypatch.setattr(main, "_process_trend_history", deque())

    forecast = main._memory_pressure_forecast(now)

    assert forecast["status"] == "elevated"
    assert forecast["rate_percent_per_minute"] > 0
    assert forecast["minutes_to_90_percent"] is not None


def test_memory_forecast_identifies_the_strongest_process_driver(monkeypatch):
    now = 3000.0
    monkeypatch.setattr(
        main,
        "_memory_usage_history",
        _memory_samples([60, 60, 61, 70, 75, 80], start=2500),
    )
    monkeypatch.setattr(
        main,
        "_process_trend_history",
        deque([
            {
                "timestamp": 1400,
                "top_cpu": [],
                "top_memory": [{
                    "pid": 42,
                    "name": "memory-leak.exe",
                    "cpu_percent": 5,
                    "memory_percent": 4,
                }],
            },
            {
                "timestamp": 2600,
                "top_cpu": [],
                "top_memory": [{
                    "pid": 42,
                    "name": "memory-leak.exe",
                    "cpu_percent": 8,
                    "memory_percent": 25,
                }],
            },
        ]),
    )

    forecast = main._memory_pressure_forecast(now)

    assert forecast["likely_process"]["name"] == "memory-leak.exe"
    assert forecast["likely_process"]["memory_risk"] == "high"


def test_memory_forecast_reports_critical_host_memory(monkeypatch):
    now = 1800.0
    monkeypatch.setattr(
        main,
        "_memory_usage_history",
        _memory_samples([92, 93, 94, 95, 95, 96], start=1500),
    )
    monkeypatch.setattr(main, "_process_trend_history", deque())

    forecast = main._memory_pressure_forecast(now)

    assert forecast["status"] == "critical"
    assert forecast["current_percent"] == 96.0
