import asyncio
import sqlite3

from backend.core.storage.db import DB_PATH, close_db, get_db, save_prediction


async def main():
    print("=== PREDICTION ACKNOWLEDGEMENT DURABILITY REGRESSION ===")

    prediction_id = "pred_ack_durability_regression_unique"

    prediction = {
        "prediction_id": prediction_id,
        "device_id": "test-device",
        "failure_type": "CRASH",
        "created_at": "2026-10-08T10:00:00+00:00",
        "expected_at": "2026-10-08T10:30:00+00:00",
        "confidence": 0.91,
        "risk_score": 0.88,
        "lead_time_seconds": 1800.0,
        "status": "active",
        "evidence": '{"test":"acknowledgement durability"}',
        "model_version": "failure-dna-regression",
        "acknowledged": False,
    }

    print("\n1. SAVING UNACKNOWLEDGED PREDICTION:")

    db = await get_db()
    assert db is not None

    await db.execute(
        "DELETE FROM predictions WHERE prediction_id = ?",
        (prediction_id,),
    )
    await db.commit()

    result = await save_prediction(prediction)

    print("save_prediction():", result)
    assert result is True

    async with db.execute(
        """
        SELECT prediction_id, acknowledged
        FROM predictions
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    print("acknowledged:", row["acknowledged"])

    assert row["acknowledged"] == 0
    print("PASS")

    print("\n2. ACKNOWLEDGING PREDICTION:")

    prediction["acknowledged"] = True

    result = await save_prediction(prediction)

    print("save_prediction() after acknowledgement:", result)
    assert result is True

    async with db.execute(
        """
        SELECT prediction_id, acknowledged
        FROM predictions
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        row = await cur.fetchone()

    assert row is not None

    print("acknowledged:", row["acknowledged"])

    assert row["acknowledged"] == 1
    print("PASS")

    print("\n3. VERIFYING DIRECT SQLITE STATE:")

    await close_db()

    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row

    direct = connection.execute(
        """
        SELECT prediction_id, failure_type, confidence, acknowledged
        FROM predictions
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ).fetchone()

    assert direct is not None

    print("prediction_id:", direct["prediction_id"])
    print("failure_type:", direct["failure_type"])
    print("confidence:", direct["confidence"])
    print("acknowledged:", direct["acknowledged"])

    assert direct["prediction_id"] == prediction_id
    assert direct["failure_type"] == "CRASH"
    assert direct["confidence"] == 0.91
    assert direct["acknowledged"] == 1

    connection.close()

    print("PASS")

    print("\n4. FRESH APPLICATION DB RELOAD:")

    fresh_db = await get_db()
    assert fresh_db is not None

    async with fresh_db.execute(
        """
        SELECT prediction_id, failure_type, confidence, acknowledged
        FROM predictions
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        fresh = await cur.fetchone()

    assert fresh is not None

    print("prediction_id:", fresh["prediction_id"])
    print("failure_type:", fresh["failure_type"])
    print("confidence:", fresh["confidence"])
    print("acknowledged:", fresh["acknowledged"])

    assert fresh["prediction_id"] == prediction_id
    assert fresh["failure_type"] == "CRASH"
    assert fresh["confidence"] == 0.91
    assert fresh["acknowledged"] == 1

    await close_db()

    print("PASS")

    print("\n5. FINAL INVARIANTS:")
    print("UNACKNOWLEDGED STATE PERSISTED: True")
    print("ACKNOWLEDGED STATE PERSISTED: True")
    print("DIRECT SQLITE SHOWS acknowledged=1: True")
    print("FRESH DB SHOWS acknowledged=1: True")
    print("PREDICTION ID STABLE: True")
    print("PREDICTION TYPE STABLE: True")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
