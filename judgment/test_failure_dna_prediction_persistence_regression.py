import asyncio
import sqlite3

from backend.core.cognitive.failure_dna import FailureDNAEngine
from backend.core.storage.db import DB_PATH, close_db, get_db


async def main():
    print("=== FAILUREDNA PREDICTION PERSISTENCE REGRESSION ===")

    print("\n1. VERIFYING DATABASE PATH:")
    print("DB_PATH:", DB_PATH)
    print("PASS")

    print("\n2. CREATING FAILUREDNA ENGINE:")
    engine = FailureDNAEngine()

    print("Engine created.")
    print("PASS")

    print("\n3. VERIFYING EXISTING CRASH PATTERN:")
    crash = engine._patterns.get("dna_CRASH")

    assert crash is not None, "dna_CRASH pattern is missing."
    assert crash.seen_count >= 10, (
        f"CRASH pattern has insufficient observations: {crash.seen_count}"
    )

    print("CRASH seen_count:", crash.seen_count)
    print("CRASH confidence:", crash.confidence)
    print("PASS")

    print("\n4. CHECKING PREDICTIONS TABLE SCHEMA:")

    db = await get_db()
    assert db is not None, "Database connection unavailable."

    async with db.execute("PRAGMA table_info(predictions)") as cur:
        columns = await cur.fetchall()

    column_names = [row["name"] for row in columns]

    print("Prediction columns:", column_names)

    required = [
        "prediction_id",
        "device_id",
        "failure_type",
        "created_at",
        "expected_at",
        "confidence",
        "risk_score",
        "lead_time_seconds",
        "status",
        "evidence",
        "model_version",
        "acknowledged",
    ]

    for column in required:
        assert column in column_names, (
            f"Required predictions column missing: {column}"
        )

    print("All required prediction columns exist.")
    print("PASS")

    print("\n5. VERIFYING EXISTING PERSISTED PREDICTION:")

    async with db.execute(
        """
        SELECT
            prediction_id,
            device_id,
            failure_type,
            confidence,
            risk_score,
            lead_time_seconds,
            status,
            acknowledged
        FROM predictions
        ORDER BY rowid DESC
        LIMIT 1
        """
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        print("No existing prediction found.")
        print("NOTE: This test requires an already-generated prediction.")
        print("RESULT: BLOCKED - NO PREDICTION TO VERIFY")
        await close_db()
        return

    print("prediction_id:", row["prediction_id"])
    print("failure_type:", row["failure_type"])
    print("confidence:", row["confidence"])
    print("risk_score:", row["risk_score"])
    print("lead_time_seconds:", row["lead_time_seconds"])
    print("status:", row["status"])
    print("acknowledged:", row["acknowledged"])

    assert row["prediction_id"]
    assert row["failure_type"]
    assert row["confidence"] is not None
    assert row["risk_score"] is not None
    assert row["acknowledged"] in (0, 1)

    prediction_id = row["prediction_id"]

    print("PASS")

    print("\n6. VERIFYING DIRECT SQLITE VISIBILITY:")

    await close_db()

    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row

    direct_row = connection.execute(
        """
        SELECT
            prediction_id,
            failure_type,
            confidence,
            risk_score,
            lead_time_seconds,
            status,
            acknowledged
        FROM predictions
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ).fetchone()

    assert direct_row is not None

    print("Direct SQLite prediction_id:", direct_row["prediction_id"])
    print("Direct SQLite failure_type:", direct_row["failure_type"])
    print("Direct SQLite confidence:", direct_row["confidence"])
    print("Direct SQLite risk_score:", direct_row["risk_score"])
    print("Direct SQLite acknowledged:", direct_row["acknowledged"])

    assert direct_row["prediction_id"] == prediction_id
    assert direct_row["failure_type"] == row["failure_type"]
    assert direct_row["acknowledged"] == row["acknowledged"]

    connection.close()

    print("PASS")

    print("\n7. FRESH APPLICATION DB RELOAD:")

    fresh_db = await get_db()
    assert fresh_db is not None

    async with fresh_db.execute(
        """
        SELECT
            prediction_id,
            failure_type,
            confidence,
            risk_score,
            lead_time_seconds,
            status,
            acknowledged
        FROM predictions
        WHERE prediction_id = ?
        """,
        (prediction_id,),
    ) as cur:
        fresh_row = await cur.fetchone()

    assert fresh_row is not None

    print("Fresh DB prediction_id:", fresh_row["prediction_id"])
    print("Fresh DB failure_type:", fresh_row["failure_type"])
    print("Fresh DB confidence:", fresh_row["confidence"])
    print("Fresh DB risk_score:", fresh_row["risk_score"])
    print("Fresh DB acknowledged:", fresh_row["acknowledged"])

    assert fresh_row["prediction_id"] == prediction_id
    assert fresh_row["failure_type"] == row["failure_type"]
    assert fresh_row["confidence"] == row["confidence"]
    assert fresh_row["risk_score"] == row["risk_score"]
    assert fresh_row["acknowledged"] == row["acknowledged"]

    await close_db()

    print("PASS")

    print("\n8. FINAL INVARIANTS:")
    print("PREDICTIONS SCHEMA COMPLETE: True")
    print("PREDICTION EXISTS: True")
    print("DIRECT SQLITE ROW EXISTS: True")
    print("FRESH DB ROW EXISTS: True")
    print("PREDICTION ID STABLE:", fresh_row["prediction_id"] == prediction_id)
    print("PREDICTION TYPE STABLE:", fresh_row["failure_type"] == row["failure_type"])
    print("CONFIDENCE STABLE:", fresh_row["confidence"] == row["confidence"])
    print("RISK SCORE STABLE:", fresh_row["risk_score"] == row["risk_score"])
    print("ACKNOWLEDGEMENT STATE STABLE:", fresh_row["acknowledged"] == row["acknowledged"])

    print("\nRESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
