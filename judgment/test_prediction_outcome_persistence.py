import asyncio
import sqlite3
import time

from backend.core.storage import db


async def main():
    print("=== PREDICTION OUTCOME / RESOLUTION PERSISTENCE TEST ===")

    prediction_id = f"outcome_test_{time.time_ns()}"
    incident_id = f"incident_test_{time.time_ns()}"

    print("\n1. CREATE PREDICTION:")

    prediction = {
        "prediction_id": prediction_id,
        "device_id": "outcome-test-device",
        "failure_type": "CRASH",
        "created_at": time.time(),
        "expected_at": time.time() + 120,
        "confidence": 0.99,
        "risk_score": 0.95,
        "lead_time_seconds": 120.0,
        "status": "active",
        "evidence": {"source": "outcome-test"},
        "model_version": "outcome-test-v1",
        "acknowledged": True,
    }

    await db.close_db()

    result = await db.save_prediction(prediction)

    print("save_prediction:", result)
    assert result is True
    print("PASS")

    print("\n2. CREATE MATCHING INCIDENT OUTCOME:")

    outcome = {
        "prediction_id": prediction_id,
        "incident_id": incident_id,
        "outcome": "true_positive",
        "lead_time_seconds": 85.0,
        "false_positive": False,
        "false_negative": False,
        "prevented": True,
        "validated_at": time.time(),
    }

    result = await db.save_prediction_outcome(outcome)

    print("save_prediction_outcome:", result)
    assert result is True
    print("PASS")

    print("\n3. VERIFY PREDICTION + OUTCOME DIRECTLY IN SQLITE:")

    await db.close_db()

    conn = sqlite3.connect(db.DB_PATH)

    try:
        prediction_row = conn.execute("""
            SELECT
                prediction_id,
                failure_type,
                status,
                confidence,
                acknowledged
            FROM predictions
            WHERE prediction_id = ?
        """, (prediction_id,)).fetchone()

        print("Prediction:", prediction_row)

        assert prediction_row is not None
        assert prediction_row[0] == prediction_id
        assert prediction_row[1] == "CRASH"
        assert prediction_row[2] == "active"
        assert prediction_row[3] == 0.99
        assert prediction_row[4] == 1

        outcome_row = conn.execute("""
            SELECT
                prediction_id,
                incident_id,
                outcome,
                lead_time_seconds,
                false_positive,
                false_negative,
                prevented
            FROM prediction_outcomes
            WHERE prediction_id = ?
        """, (prediction_id,)).fetchone()

        print("Outcome:", outcome_row)

        assert outcome_row is not None
        assert outcome_row[0] == prediction_id
        assert outcome_row[1] == incident_id
        assert outcome_row[2] == "true_positive"
        assert outcome_row[3] == 85.0
        assert outcome_row[4] == 0
        assert outcome_row[5] == 0
        assert outcome_row[6] == 1

        print("PASS: prediction and outcome are both durable.")
    finally:
        conn.close()

    print("\n4. FRESH APPLICATION DB CONNECTION:")

    reopened = await db.get_db()
    assert reopened is not None

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
    assert loaded["acknowledged"] == 1

    print("PASS: prediction survives fresh application connection.")

    await db.close_db()

    print("\n5. FINAL RESULT:")
    print("PASS: PREDICTION + OUTCOME PERSISTENCE VERIFIED.")
    print("Prediction -> outcome -> SQLite -> fresh application connection: verified.")


if __name__ == "__main__":
    asyncio.run(main())
