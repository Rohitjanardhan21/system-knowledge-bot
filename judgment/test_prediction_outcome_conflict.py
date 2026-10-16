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
    print("=== PREDICTION OUTCOME CONFLICT REGRESSION ===")

    prediction_id = "pred_outcome_conflict_regression_unique"
    incident_id = "incident_outcome_conflict_regression_unique"

    prediction = {
        "prediction_id": prediction_id,
        "device_id": "test-device",
        "failure_type": "CRASH",
        "created_at": "2026-10-08T10:00:00+00:00",
        "expected_at": "2026-10-08T10:30:00+00:00",
        "confidence": 0.95,
        "risk_score": 0.92,
        "lead_time_seconds": 1800.0,
        "status": "active",
        "evidence": '{"test":"outcome conflict"}',
        "model_version": "failure-dna-regression",
        "acknowledged": True,
    }

    true_positive = {
        "prediction_id": prediction_id,
        "incident_id": incident_id,
        "outcome": "true_positive",
        "lead_time_seconds": 700.0,
        "false_positive": False,
        "false_negative": False,
        "prevented": True,
    }

    conflicting_outcome = {
        "prediction_id": prediction_id,
        "incident_id": incident_id,
        "outcome": "false_positive",
        "lead_time_seconds": 0.0,
        "false_positive": True,
        "false_negative": False,
        "prevented": False,
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

    print("\n2. WRITING INITIAL TRUE-POSITIVE OUTCOME:")

    result = await save_prediction_outcome(true_positive)

    print("save_prediction_outcome():", result)
    assert result is True

    async with db.execute(
        """
        SELECT
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
        original = await cur.fetchone()

    assert original is not None
    assert original["outcome"] == "true_positive"
    assert original["prevented"] == 1

    print("Original outcome:", original["outcome"])
    print("Original lead time:", original["lead_time_seconds"])
    print("Original prevented:", original["prevented"])
    print("PASS")

    print("\n3. SUBMITTING CONFLICTING FALSE-POSITIVE OUTCOME:")

    conflict_result = await save_prediction_outcome(conflicting_outcome)

    print("save_prediction_outcome() returned:", conflict_result)

    print("\n4. CHECKING DATABASE AFTER CONFLICT:")

    async with db.execute(
        """
        SELECT COUNT(*) AS count
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        count_row = await cur.fetchone()

    row_count = count_row["count"]

    print("Outcome row count:", row_count)

    assert row_count == 1
    print("PASS: no duplicate outcome row created.")

    async with db.execute(
        """
        SELECT
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
        final_row = await cur.fetchone()

    assert final_row is not None

    print("Final outcome:", final_row["outcome"])
    print("Final lead time:", final_row["lead_time_seconds"])
    print("Final false_positive:", final_row["false_positive"])
    print("Final false_negative:", final_row["false_negative"])
    print("Final prevented:", final_row["prevented"])

    print("\n5. DETERMINING CONFLICT BEHAVIOR:")

    unchanged = (
        final_row["outcome"] == "true_positive"
        and final_row["lead_time_seconds"] == 700.0
        and final_row["false_positive"] == 0
        and final_row["false_negative"] == 0
        and final_row["prevented"] == 1
    )

    print("Original outcome preserved:", unchanged)
    print("Conflict call returned:", conflict_result)

    if unchanged:
        print("PASS: conflicting outcome was rejected/ignored safely.")
    else:
        print(
            "BUG CONFIRMED: conflicting outcome overwrote "
            "the previously validated outcome."
        )

    assert unchanged, (
        "prediction outcome was silently changed by a conflicting write"
    )

    print("\n6. DIRECT SQLITE VERIFICATION:")

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

    direct = connection.execute(
        """
        SELECT outcome, lead_time_seconds, prevented
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ).fetchone()

    print("Direct row count:", direct_count)
    print("Direct outcome:", direct["outcome"])
    print("Direct lead time:", direct["lead_time_seconds"])
    print("Direct prevented:", direct["prevented"])

    assert direct_count == 1
    assert direct["outcome"] == "true_positive"
    assert direct["lead_time_seconds"] == 700.0
    assert direct["prevented"] == 1

    connection.close()

    print("PASS")

    print("\n7. FRESH DB VERIFICATION:")

    fresh_db = await get_db()
    assert fresh_db is not None

    async with fresh_db.execute(
        """
        SELECT outcome, lead_time_seconds, prevented
        FROM prediction_outcomes
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        fresh = await cur.fetchone()

    assert fresh is not None

    print("Fresh outcome:", fresh["outcome"])
    print("Fresh lead time:", fresh["lead_time_seconds"])
    print("Fresh prevented:", fresh["prevented"])

    assert fresh["outcome"] == "true_positive"
    assert fresh["lead_time_seconds"] == 700.0
    assert fresh["prevented"] == 1

    await close_db()

    print("PASS")

    print("\n8. FINAL INVARIANTS:")
    print("ONLY ONE OUTCOME ROW EXISTS:", row_count == 1)
    print("ORIGINAL OUTCOME PRESERVED:", unchanged)
    print("ORIGINAL LEAD TIME PRESERVED:", final_row["lead_time_seconds"] == 700.0)
    print("ORIGINAL PREVENTED FLAG PRESERVED:", final_row["prevented"] == 1)
    print("DIRECT SQLITE CONSISTENT:", direct["outcome"] == "true_positive")
    print("FRESH DB CONSISTENT:", fresh["outcome"] == "true_positive")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
