import asyncio
import sqlite3

from backend.core.storage.db import (
    DB_PATH,
    close_db,
    get_db,
    save_prediction,
    save_prediction_outcome,
)


async def main():
    print("=== PREDICTION OUTCOME IDEMPOTENCY REGRESSION ===")

    prediction_id = "pred_outcome_idempotency_regression_unique"
    incident_id = "incident_outcome_idempotency_regression_unique"

    prediction = {
        "prediction_id": prediction_id,
        "device_id": "test-device",
        "failure_type": "CRASH",
        "created_at": "2026-10-08T10:00:00+00:00",
        "expected_at": "2026-10-08T10:30:00+00:00",
        "confidence": 0.93,
        "risk_score": 0.90,
        "lead_time_seconds": 1800.0,
        "status": "active",
        "evidence": '{"test":"outcome idempotency"}',
        "model_version": "failure-dna-regression",
        "acknowledged": True,
    }

    outcome = {
        "prediction_id": prediction_id,
        "incident_id": incident_id,
        "outcome": "true_positive",
        "lead_time_seconds": 721.0,
        "false_positive": False,
        "false_negative": False,
        "prevented": True,
    }

    print("\n1. CREATING CLEAN TEST PREDICTION:")

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

    print("\n2. FIRST OUTCOME WRITE:")

    result = await save_prediction_outcome(outcome)

    print("save_prediction_outcome():", result)
    assert result is True

    async with db.execute(
        """
        SELECT COUNT(*) AS count
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        row = await cur.fetchone()

    first_count = row["count"]

    print("Outcome rows after first write:", first_count)

    assert first_count == 1
    print("PASS")

    print("\n3. SECOND IDENTICAL OUTCOME WRITE:")

    result = await save_prediction_outcome(outcome)

    print("save_prediction_outcome():", result)
    assert result is True

    async with db.execute(
        """
        SELECT COUNT(*) AS count
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        row = await cur.fetchone()

    second_count = row["count"]

    print("Outcome rows after second write:", second_count)

    assert second_count == 1
    print("PASS: duplicate outcome was not created.")

    print("\n4. VERIFYING STORED OUTCOME:")

    async with db.execute(
        """
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
        """,
        (prediction_id,),
    ) as cur:
        stored = await cur.fetchone()

    assert stored is not None

    print("prediction_id:", stored["prediction_id"])
    print("incident_id:", stored["incident_id"])
    print("outcome:", stored["outcome"])
    print("lead_time_seconds:", stored["lead_time_seconds"])
    print("false_positive:", stored["false_positive"])
    print("false_negative:", stored["false_negative"])
    print("prevented:", stored["prevented"])

    assert stored["prediction_id"] == prediction_id
    assert stored["incident_id"] == incident_id
    assert stored["outcome"] == "true_positive"
    assert stored["lead_time_seconds"] == 721.0
    assert stored["false_positive"] == 0
    assert stored["false_negative"] == 0
    assert stored["prevented"] == 1

    print("PASS")

    print("\n5. DIRECT SQLITE DUPLICATION CHECK:")

    await close_db()

    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row

    direct_count = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ).fetchone()["count"]

    print("Direct SQLite outcome rows:", direct_count)

    assert direct_count == 1

    direct = connection.execute(
        """
        SELECT prediction_id, incident_id, outcome, prevented
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ).fetchone()

    assert direct["prediction_id"] == prediction_id
    assert direct["incident_id"] == incident_id
    assert direct["outcome"] == "true_positive"
    assert direct["prevented"] == 1

    connection.close()

    print("PASS")

    print("\n6. FRESH APPLICATION DB CHECK:")

    fresh_db = await get_db()
    assert fresh_db is not None

    async with fresh_db.execute(
        """
        SELECT COUNT(*) AS count
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        fresh_count_row = await cur.fetchone()

    fresh_count = fresh_count_row["count"]

    print("Fresh DB outcome rows:", fresh_count)

    assert fresh_count == 1

    await close_db()

    print("PASS")

    print("\n7. FINAL INVARIANTS:")
    print("FIRST OUTCOME CREATED ONCE:", first_count == 1)
    print("SECOND IDENTICAL WRITE DID NOT DUPLICATE:", second_count == 1)
    print("DIRECT SQLITE HAS ONE ROW:", direct_count == 1)
    print("FRESH DB HAS ONE ROW:", fresh_count == 1)
    print("OUTCOME CONTENT PRESERVED:", True)

    assert first_count == 1
    assert second_count == 1
    assert direct_count == 1
    assert fresh_count == 1

    print("\nRESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
