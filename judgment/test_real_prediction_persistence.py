import asyncio
import sqlite3
import time

from backend.core.storage import db


async def main():
    print("=== REAL PREDICTION PERSISTENCE TEST ===")

    await db.close_db()

    print("\n1. OPENING DATABASE / RUNNING MIGRATION:")
    conn = sqlite3.connect(db.DB_PATH)
    try:
        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(predictions)")
        ]
        print("Prediction columns:", columns)
        assert "acknowledged" in columns
        print("PASS: acknowledged column exists.")
    finally:
        conn.close()

    prediction_id = f"persistence_test_{time.time_ns()}"

    prediction = {
        "prediction_id": prediction_id,
        "device_id": "persistence-test-device",
        "failure_type": "CRASH",
        "created_at": time.time(),
        "expected_at": time.time() + 60,
        "confidence": 0.99,
        "risk_score": 0.95,
        "lead_time_seconds": 60.0,
        "status": "active",
        "evidence": {
            "source": "real-persistence-test",
            "test": True,
        },
        "model_version": "persistence-test-v1",
        "acknowledged": False,
    }

    print("\n2. SAVING PREDICTION:")
    print("prediction_id:", prediction_id)

    result = await db.save_prediction(prediction)

    print("save_prediction returned:", result)
    assert result is True
    print("PASS: prediction persisted.")

    print("\n3. READING DIRECTLY FROM SQLITE:")

    await db.close_db()

    conn = sqlite3.connect(db.DB_PATH)
    try:
        row = conn.execute("""
            SELECT
                prediction_id,
                device_id,
                failure_type,
                confidence,
                risk_score,
                status,
                model_version,
                acknowledged
            FROM predictions
            WHERE prediction_id = ?
        """, (prediction_id,)).fetchone()

        print(row)

        assert row is not None
        assert row[0] == prediction_id
        assert row[1] == "persistence-test-device"
        assert row[2] == "CRASH"
        assert row[3] == 0.99
        assert row[4] == 0.95
        assert row[5] == "active"
        assert row[6] == "persistence-test-v1"
        assert row[7] == 0

        print("PASS: all persisted fields are correct.")
    finally:
        conn.close()

    print("\n4. REOPENING THROUGH APPLICATION DB LAYER:")

    reopened = await db.get_db()
    assert reopened is not None

    active = await db.load_active_predictions()

    matches = [
        p for p in active
        if p.get("prediction_id") == prediction_id
    ]

    print("Matching active predictions:", len(matches))

    assert len(matches) == 1

    loaded = matches[0]

    print("Loaded prediction:")
    print(loaded)

    assert loaded["acknowledged"] == 0
    assert loaded["failure_type"] == "CRASH"
    assert loaded["confidence"] == 0.99

    print("PASS: application layer reloads the persisted prediction.")

    await db.close_db()

    print("\n5. FINAL RESULT:")
    print("PASS: REAL PREDICTION PERSISTENCE IS WORKING.")
    print("Migration + save_prediction + SQLite durability + reload all verified.")


if __name__ == "__main__":
    asyncio.run(main())
