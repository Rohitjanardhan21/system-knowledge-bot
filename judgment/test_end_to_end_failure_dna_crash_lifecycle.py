import asyncio
import multiprocessing
import sqlite3
import time

from backend.core.cognitive.failure_dna import FailureDNAEngine
from backend.core.storage import db


def crashing_application():
    print("CHILD APPLICATION: STARTED", flush=True)
    time.sleep(0.5)
    print("CHILD APPLICATION: CRASHING", flush=True)
    raise RuntimeError("intentional application crash for lifecycle test")


async def main():
    print("=== END-TO-END FAILUREDNA CRASH LIFECYCLE V3 ===")

    engine = FailureDNAEngine()

    print("\n1. BUILDING BASELINE:")

    engine._baseline_stats = {}
    engine._metric_buffer.clear()

    for i in range(30):
        metrics = {
            "cpu_percent": 25.0 + (i % 3) * 0.2,
            "memory": 40.0 + (i % 2) * 0.2,
            "disk_percent": 35.0 + (i % 2) * 0.2,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        }

        engine._update_baseline(
            engine._extract_snapshot(metrics)
        )

    print("PASS: baseline populated.")

    print("\n2. LOCATING CRASH PATTERN:")

    crash = None

    for pattern in engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == "dna_CRASH":
            crash = pattern
            break

    assert crash is not None

    print(
        "CRASH pattern:",
        crash.pattern_id,
        "| seen=",
        crash.seen_count,
        "| confidence=",
        crash.confidence,
    )

    print("PASS")

    print("\n3. SEEDING SIX NORMAL OBSERVATIONS:")

    for _ in range(6):
        metrics = {
            "cpu_percent": 25.0,
            "memory": 40.0,
            "disk_percent": 35.0,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        }

        engine.ingest(metrics)

    assert len(engine._metric_buffer) == 6

    print("Buffer:", len(engine._metric_buffer))
    print("PASS")

    print("\n4. BUILDING CRASH SIGNATURE FROM ACTUAL BASELINE:")

    internal_keys = [
        "cpu",
        "mem",
        "disk",
        "net",
        "anomaly",
    ]

    raw_keys = [
        "cpu_percent",
        "memory",
        "disk_percent",
        "network_percent",
        "anomaly_score",
    ]

    means = {
        key: engine._baseline_stats[key]["mean"]
        for key in internal_keys
    }

    stds = {
        key: engine._baseline_stats[key]["std"]
        for key in internal_keys
    }

    for key in internal_keys:
        if stds[key] <= 0:
            stds[key] = 0.1

    prediction = None

    for index, step in enumerate(crash.signature_steps, 1):

        internal_values = {
            key: means[key] + step[position] * stds[key]
            for position, key in enumerate(internal_keys)
        }

        metrics = dict(
            zip(
                raw_keys,
                internal_values.values(),
            )
        )

        engine.ingest(metrics)

        confidence, eta = engine._match_pattern(
            crash,
            list(engine._metric_buffer),
        )

        print(
            f"Step {index}: "
            f"buffer={len(engine._metric_buffer)} "
            f"confidence={confidence:.4f} "
            f"eta={eta:.2f}"
        )

    confidence, eta = engine._match_pattern(
        crash,
        list(engine._metric_buffer),
    )

    print("Final CRASH matcher confidence:", confidence)
    print("Final CRASH matcher ETA:", eta)

    assert confidence > 0.0

    print("PASS: CRASH matcher reproduced.")

    print("\n5. GENERATING ACTUAL FAILUREDNA PREDICTION:")

    final_metrics = {
        "cpu_percent": internal_values["cpu"],
        "memory": internal_values["mem"],
        "disk_percent": internal_values["disk"],
        "network_percent": internal_values["net"],
        "anomaly_score": internal_values["anomaly"],
    }

    prediction = engine.predict(final_metrics)

    assert prediction is not None

    print(
        "Prediction:",
        prediction.prediction_id,
        "| type=",
        prediction.failure_type,
        "| confidence=",
        prediction.confidence,
    )

    assert prediction.failure_type == "CRASH"

    prediction_id = prediction.prediction_id

    print("PASS: actual FailureDNA prediction is CRASH.")

    print("\n6. ALLOWING PERSISTENCE TO COMPLETE:")

    await asyncio.sleep(0.5)

    active = await db.load_active_predictions()

    matches = [
        p for p in active
        if p.get("prediction_id") == prediction_id
    ]

    print("Persisted matches:", len(matches))

    assert len(matches) == 1

    persisted = matches[0]

    print(persisted)

    assert persisted["failure_type"] == "CRASH"
    assert persisted["acknowledged"] == 0

    print("PASS: CRASH prediction persisted.")

    print("\n7. ACKNOWLEDGING PREDICTION:")

    persisted["acknowledged"] = True

    result = await db.save_prediction(persisted)

    print("save_prediction:", result)

    assert result is True

    print("PASS")

    print("\n8. STARTING REAL CHILD APPLICATION:")

    multiprocessing.freeze_support()

    process = multiprocessing.Process(
        target=crashing_application,
        name="FailureDNA-Crash-Test",
    )

    process.start()

    print("Child PID:", process.pid)

    process.join(timeout=10)

    assert not process.is_alive()

    print("Child exitcode:", process.exitcode)

    assert process.exitcode != 0

    print("PASS: real child application crashed.")

    print("\n9. RECORDING PROCESS_CRASH:")

    engine.record_failure(
        "PROCESS_CRASH",
        f"FailureDNA lifecycle child process {process.pid} terminated unexpectedly",
        severity="HIGH",
    )

    history = engine.get_failure_history(limit=50)

    matching_events = [
        event
        for event in history
        if getattr(event, "event_type", None) == "PROCESS_CRASH"
        and str(process.pid) in getattr(event, "description", "")
    ]

    print("Matching crash events:", len(matching_events))

    assert matching_events

    crash_event = matching_events[0]

    print(
        "Crash event:",
        crash_event.event_id,
        "|",
        crash_event.event_type,
        "|",
        crash_event.severity,
    )

    print("PASS")

    print("\n10. RECORDING TRUE-POSITIVE OUTCOME:")

    incident_id = f"incident_{time.time_ns()}"

    outcome = {
        "prediction_id": prediction_id,
        "incident_id": incident_id,
        "outcome": "true_positive",
        "lead_time_seconds": float(
            getattr(prediction, "minutes_remaining", 0.0) * 60.0
        ),
        "false_positive": False,
        "false_negative": False,
        "prevented": False,
        "validated_at": time.time(),
    }

    result = await db.save_prediction_outcome(outcome)

    print("save_prediction_outcome:", result)

    assert result is True

    print("PASS")

    print("\n11. FRESH DATABASE CONNECTION:")

    await db.close_db()

    fresh = await db.get_db()

    assert fresh is not None

    active = await db.load_active_predictions()

    matches = [
        p for p in active
        if p.get("prediction_id") == prediction_id
    ]

    assert len(matches) == 1

    loaded = matches[0]

    print("Reloaded prediction:")
    print(loaded)

    assert loaded["prediction_id"] == prediction_id
    assert loaded["failure_type"] == "CRASH"
    assert loaded["acknowledged"] == 1

    print("PASS: prediction survived fresh DB connection.")

    print("\n12. VERIFYING OUTCOME:")

    await db.close_db()

    conn = sqlite3.connect(db.DB_PATH)

    try:
        row = conn.execute("""
            SELECT
                prediction_id,
                incident_id,
                outcome,
                false_positive,
                false_negative,
                prevented
            FROM prediction_outcomes
            WHERE prediction_id = ?
        """, (prediction_id,)).fetchone()

        print(row)

        assert row is not None
        assert row[0] == prediction_id
        assert row[1] == incident_id
        assert row[2] == "true_positive"
        assert row[3] == 0
        assert row[4] == 0
        assert row[5] == 0

        print("PASS: outcome is durable.")

    finally:
        conn.close()

    print("\n13. FINAL END-TO-END INVARIANTS:")
    print("CRASH SIGNATURE MATCHED")
    print("FAILUREDNA CRASH PREDICTION GENERATED")
    print("CRASH PREDICTION PERSISTED")
    print("PREDICTION ACKNOWLEDGED")
    print("REAL CHILD APPLICATION CRASHED")
    print("PROCESS_CRASH RECORDED")
    print("TRUE-POSITIVE OUTCOME PERSISTED")
    print("FRESH DB CONNECTION OBSERVED PREDICTION")
    print("DATABASE OBSERVED OUTCOME")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
