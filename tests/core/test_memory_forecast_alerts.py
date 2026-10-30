import asyncio
from unittest.mock import AsyncMock

from backend.core.alerts.alert_engine import AlertEngine


def test_memory_forecast_alert_includes_process_and_deduplicates():
    engine = AlertEngine()
    engine._dispatch = AsyncMock()
    metrics = {
        "memory_forecast_level": 1,
        "memory_forecast_process": "memory-leak.exe",
    }

    asyncio.run(engine.evaluate(metrics))
    asyncio.run(engine.evaluate(metrics))

    alerts = [
        alert for alert in engine.history
        if alert.rule_id == "r_mem_forecast_warn"
    ]
    assert len(alerts) == 1
    assert alerts[0].severity == "WARNING"
    assert "memory-leak.exe" in alerts[0].message


def test_critical_memory_forecast_fires_critical_alert():
    engine = AlertEngine()
    engine._dispatch = AsyncMock()

    asyncio.run(engine.evaluate({
        "memory_forecast_level": 2,
        "memory_forecast_process": "memory-leak.exe",
    }))

    critical = [
        alert for alert in engine.history
        if alert.rule_id == "r_mem_forecast_crit"
    ]
    assert len(critical) == 1
    assert critical[0].severity == "CRITICAL"
