import asyncio
import sqlite3

from backend.core.storage.db import DB_PATH, close_db, get_db, save_prediction, save_prediction_outcome


async def main():
    print("=== PREDICTION OUTCOME DURABILITY REGRESSION ===")

    prediction_id = "pred_outcome_durability_regression_unique"
    incident_id = "incident_outcome_durability_regression_unique"

    prediction = {
        "prediction_id": prediction_id,
        "device_id": "test-device",
        "failure_type": "CRASH",
        "created_at": "2026-10-08T10:00:00+00:00",
        "expected_at": "2026-10-08T10:30:00+00:00",
        "confidence": 0.94,
        "risk_score": 0.91,
        "lead_time_seconds": 1800.0,
        "status": "active",
        "evidence": '{"test":"outcome durability"}',
        "model_version": "failure-dna-regression",
        "acknowledged": True,
    }

    print("\n1. CREATING TEST PREDICTION:")

    db = await get_db()
    assert db is not None

    await db.execute(
        "DELETE FROM predictions WHERE prediction_id = ?",
        (prediction_id,),
    )

    await db.execute(
        "DELETE FROM prediction_outcomes WHERE prediction_id = ?",
        (prediction_id,),
    )

    await db.commit()

    result = await save_prediction(prediction)

    print("save_prediction():", result)
    assert result is True
    print("PASS")

    print("\n2. RECORDING TRUE-POSITIVE OUTCOME:")

    outcome = {
        "prediction_id": prediction_id,
        "incident_id": incident_id,
        "outcome": "true_positive",
        "lead_time_seconds": 847.0,
        "false_positive": False,
        "false_negative": False,
        "prevented": True,
    }

    result = await save_prediction_outcome(outcome)

    print("save_prediction_outcome():", result)
    assert result is True
    print("PASS")

    print("\n3. VERIFYING LIVE DATABASE:")

    async with db.execute(
        """
        SELECT
            prediction_id,
            incident_id,
            outcome,
            lead_time_seconds,
            false_positive,
            false_negative,
            prevented,
            validated_at
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        row = await cur.fetchone()

    assert row is not None

    print("prediction_id:", row["prediction_id"])
    print("incident_id:", row["incident_id"])
    print("outcome:", row["outcome"])
    print("lead_time_seconds:", row["lead_time_seconds"])
    print("false_positive:", row["false_positive"])
    print("false_negative:", row["false_negative"])
    print("prevented:", row["prevented"])
    print("validated_at:", row["validated_at"])

    assert row["prediction_id"] == prediction_id
    assert row["incident_id"] == incident_id
    assert row["outcome"] == "true_positive"
    assert row["lead_time_seconds"] == 847.0
    assert row["false_positive"] == 0
    assert row["false_negative"] == 0
    assert row["prevented"] == 1
    assert row["validated_at"]

    print("PASS")

    print("\n4. VERIFYING DIRECT SQLITE STATE:")

    await close_db()

    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row

    direct = connection.execute(
        """
        SELECT
            prediction_id,
            incident_id,
            outcome,
            lead_time_seconds,
            false_positive,
            false_negative,
            prevented,
            validated_at
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ).fetchone()

    assert direct is not None

    print("Direct SQLite prediction_id:", direct["prediction_id"])
    print("Direct SQLite incident_id:", direct["incident_id"])
    print("Direct SQLite outcome:", direct["outcome"])
    print("Direct SQLite lead time:", direct["lead_time_seconds"])
    print("Direct SQLite prevented:", direct["prevented"])

    assert direct["prediction_id"] == prediction_id
    assert direct["incident_id"] == incident_id
    assert direct["outcome"] == "true_positive"
    assert direct["lead_time_seconds"] == 847.0
    assert direct["prevented"] == 1

    connection.close()

    print("PASS")

    print("\n5. FRESH APPLICATION DB RELOAD:")

    fresh_db = await get_db()
    assert fresh_db is not None

    async with fresh_db.execute(
        """
        SELECT
            prediction_id,
            incident_id,
            outcome,
            lead_time_seconds,
            false_positive,
            false_negative,
            prevented,
            validated_at
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        fresh = await cur.fetchone()

    assert fresh is not None

    print("Fresh DB prediction_id:", fresh["prediction_id"])
    print("Fresh DB incident_id:", fresh["incident_id"])
    print("Fresh DB outcome:", fresh["outcome"])
    print("Fresh DB lead time:", fresh["lead_time_seconds"])
    print("Fresh DB prevented:", fresh["prevented"])
    print("Fresh DB validated_at:", fresh["validated_at"])

    assert fresh["prediction_id"] == prediction_id
    assert fresh["incident_id"] == incident_id
    assert fresh["outcome"] == "true_positive"
    assert fresh["lead_time_seconds"] == 847.0
    assert fresh["false_positive"] == 0
    assert fresh["false_negative"] == 0
    assert fresh["prevented"] == 1
    assert fresh["validated_at"]

    await close_db()

    print("PASS")

    print("\n6. FINAL INVARIANTS:")
    print("PREDICTION CREATED: True")
    print("TRUE-POSITIVE OUTCOME STORED: True")
    print("LEAD TIME PRESERVED: True")
    print("PREVENTED FLAG PRESERVED: True")
    print("DIRECT SQLITE ROW EXISTS: True")
    print("FRESH DB ROW EXISTS: True")
    print("PREDICTION ID STABLE: True")
    print("INCIDENT ID STABLE: True")
    print("VALIDATION TIMESTAMP EXISTS: True")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
