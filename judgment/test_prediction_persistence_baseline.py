import asyncio
import sqlite3
from pathlib import Path

from backend.core.storage import db


async def run_test():
    print("=== REAL PREDICTION PERSISTENCE BASELINE ===")

    print("\n=== DATABASE ===")
    print("DB_PATH:", db.DB_PATH)

    await db.close_db()

    conn = sqlite3.connect(db.DB_PATH)
    try:
        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(predictions)")
        ]
        print("Prediction columns:")
        for column in columns:
            print(" ", column)

        print("\nacknowledged present:", "acknowledged" in columns)
    finally:
        conn.close()

    print("\n=== save_prediction() ===")

    prediction = {
        "prediction_id": "schema_baseline_test",
        "device_id": "test-device",
        "failure_type": "CRASH",
        "created_at": 1000.0,
        "expected_at": 1060.0,
        "confidence": 0.99,
        "risk_score": 0.95,
        "lead_time_seconds": 60.0,
        "status": "active",
        "evidence": {"source": "schema-baseline"},
        "model_version": "test-v1",
        "acknowledged": False,
    }

    result = await db.save_prediction(prediction)

    print("save_prediction returned:", result)

    await db.close_db()

    print("\n=== RESULT ===")

    # get_db() migrates the schema lazily, so the pre-save column check may
    # still lack the column; verify the post-save state instead.
    assert result is True

    conn = sqlite3.connect(db.DB_PATH)
    try:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(predictions)")]
        assert "acknowledged" in columns
        row = conn.execute(
            "SELECT acknowledged FROM predictions WHERE prediction_id = ?",
            (prediction["prediction_id"],),
        ).fetchone()
        assert row is not None and row[0] == 0
        conn.execute(
            "DELETE FROM predictions WHERE prediction_id = ?",
            (prediction["prediction_id"],),
        )
        conn.commit()
    finally:
        conn.close()
    print("PASS: migration added acknowledged and prediction persisted.")

    print("\n=== TEST COMPLETE ===")


def main():
    asyncio.run(run_test())


if __name__ == "__main__":
    main()
