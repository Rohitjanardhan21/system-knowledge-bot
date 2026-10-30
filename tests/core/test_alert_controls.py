import asyncio
import time
from pathlib import Path

from backend.core.alerts.alert_engine import AlertEngine, FiredAlert
from backend.core.storage import db


def _run(coro):
    return asyncio.run(coro)


def test_alert_acknowledge_and_snooze_persist(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "alerts.db"
    monkeypatch.setattr(db, "DB_PATH", str(database_path))
    _run(db.close_db())

    alert = FiredAlert(
        alert_id="alert-1",
        rule_id="r_mem_forecast_warn",
        severity="WARNING",
        message="Memory pressure is rising",
        metrics={"memory_forecast_level": 1},
        fired_at=100.0,
    )

    try:
        assert _run(db.save_alert(alert)) is True
        assert _run(db.acknowledge_alert("alert-1", 200.0)) is True
        assert _run(db.snooze_alert("alert-1", 500.0)) is True

        async def read_control_state():
            connection = await db.get_db()
            async with connection.execute(
                """
                SELECT acknowledged_at, snoozed_until
                FROM alerts
                WHERE id = ?
                """,
                ("alert-1",),
            ) as cursor:
                return await cursor.fetchone()

        row = _run(read_control_state())
        assert row["acknowledged_at"] == 200.0
        assert row["snoozed_until"] == 500.0
    finally:
        _run(db.close_db())


def test_process_suppression_persists_and_expired_entries_are_removed(
    tmp_path: Path,
    monkeypatch,
):
    database_path = tmp_path / "suppressions.db"
    monkeypatch.setattr(db, "DB_PATH", str(database_path))
    _run(db.close_db())

    try:
        assert _run(db.save_process_suppression("memory-leak.exe", 200.0))
        assert _run(db.save_process_suppression("old-process.exe", 50.0))

        suppressions = _run(db.load_process_suppressions(100.0))

        assert suppressions == {"memory-leak.exe": 200.0}
    finally:
        _run(db.close_db())


def test_process_suppression_prevents_forecast_alert_until_restored():
    engine = AlertEngine()
    engine.set_process_suppression("memory-leak.exe", time.time() + 60)

    _run(
        engine.evaluate(
            {
                "memory_forecast_level": 2,
                "memory_forecast_process": "memory-leak.exe",
            }
        )
    )

    assert not engine.history

    engine.restore_process_suppressions({})
    _run(
        engine.evaluate(
            {
                "memory_forecast_level": 2,
                "memory_forecast_process": "memory-leak.exe",
            }
        )
    )

    assert {
        alert.rule_id for alert in engine.history
    } == {"r_mem_forecast_warn", "r_mem_forecast_crit"}
