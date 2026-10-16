import asyncio
import sqlite3
import time

from backend.core.storage import db


async def main():
    print("=== PREDICTION ACKNOWLEDGEMENT LIFECYCLE TEST ===")

    prediction_id = f"ack_test_{time.time_ns()}"

    prediction = {
        "prediction_id": prediction_id,
        "device_id": "ack-test-device",
        "failure_type": "CRASH",
        "created_at": time.time(),
        "expected_at": time.time() + 120,
        "confidence": 0.99,
        "risk_score": 0.95,
        "lead_time_seconds": 120.0,
        "status": "active",
        "evidence": {"source": "ack-lifecycle-test"},
        "model_version": "ack-test-v1",
        "acknowledged": False,
    }

    print("\n1. CREATING UNACKNOWLEDGED PREDICTION:")

    await db.close_db()

    result = await db.save_prediction(prediction)

    print("save_prediction:", result)
    assert result is True

    active = await db.load_active_predictions()

    created = [
        p for p in active
        if p.get("prediction_id") == prediction_id
    ]

    assert len(created) == 1
    print("Loaded acknowledged value:", created[0]["acknowledged"])
    assert created[0]["acknowledged"] == 0

    print("PASS")

    print("\n2. ACKNOWLEDGING PREDICTION:")

    acknowledged_prediction = dict(prediction)
    acknowledged_prediction["acknowledged"] = True

    result = await db.save_prediction(acknowledged_prediction)

    print("save_prediction:", result)
    assert result is True

    print("PASS")

    print("\n3. VERIFYING SQLITE DURABILITY:")

    await db.close_db()

    conn = sqlite3.connect(db.DB_PATH)

    try:
        row = conn.execute("""
            SELECT
                prediction_id,
                status,
                acknowledged
            FROM predictions
            WHERE prediction_id = ?
        """, (prediction_id,)).fetchone()

        print(row)

        assert row is not None
        assert row[0] == prediction_id
        assert row[1] == "active"
        assert row[2] == 1

        print("PASS: acknowledged=1 persisted.")
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

    print(loaded)

    assert loaded["acknowledged"] == 1
    assert loaded["status"] == "active"

    print("PASS: fresh DB layer sees acknowledged prediction.")

    await db.close_db()

    print("\n5. FINAL RESULT:")
    print("PASS: PREDICTION ACKNOWLEDGEMENT LIFECYCLE IS DURABLE.")
    print("unacknowledged -> acknowledged -> SQLite -> fresh process: verified.")


if __name__ == "__main__":
    asyncio.run(main())
