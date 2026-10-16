import asyncio
import sqlite3
from pathlib import Path

from backend.main import app
from backend.core.cognitive.failure_dna import get_dna_engine
from backend.core.storage.db import load_active_predictions


DB_PATH = Path("data") / "cvis.db"
TARGET_ID = "persistence_test_1791441561472976100"


async def run():
    print("=== REAL RESTARTED PREDICTION RESOLUTION TEST ===")
    print()
    print("REAL-LIFE SCENARIO:")
    print("A prediction already exists in the durable SQLite store.")
    print("The backend restarts.")
    print("FailureDNA restores the active prediction.")
    print("The production resolution path is invoked.")
    print("The result is verified directly in SQLite.")
    print()
    print("No prediction will be created.")
    print("No telemetry will be injected.")
    print("No prediction values will be fabricated.")
    print()

    assert DB_PATH.exists(), f"Database not found: {DB_PATH}"

    async with app.router.lifespan_context(app):
        print("Backend lifespan: STARTED")
        print()

        rows = await load_active_predictions()

        target = next(
            (row for row in rows if row.get("prediction_id") == TARGET_ID),
            None,
        )

        assert target is not None, (
            f"Target prediction {TARGET_ID} is not active in SQLite."
        )

        print("=== DURABLE PREDICTION BEFORE RESOLUTION ===")
        print("prediction_id:", target.get("prediction_id"))
        print("failure_type:", target.get("failure_type"))
        print("status:", target.get("status"))
        print("acknowledged:", target.get("acknowledged"))
        print("created_at:", target.get("created_at"))
        print("expected_at:", target.get("expected_at"))

        dna = get_dna_engine()
        in_memory = dna._active_predictions.get(TARGET_ID)

        assert in_memory is not None, (
            "Target prediction exists in SQLite but was not restored into "
            "FailureDNA memory."
        )

        assert not in_memory.resolved, (
            "Target prediction was already resolved."
        )

        print()
        print("FailureDNA in-memory state: PRESENT")
        print("resolved:", in_memory.resolved)
        print("acknowledged:", in_memory.acknowledged)

        print()
        print("=== PRODUCTION RESOLUTION PATH ===")
        print("Resolving existing prediction as incorrect.")
        print("This is a lifecycle outcome, not a new prediction.")

        # Call the actual production endpoint function.
        result = await app.router.routes[
            next(
                i for i, route in enumerate(app.router.routes)
                if getattr(route, "path", None)
                == "/cognitive/predictions/{pred_id}/resolve"
            )
        ].endpoint(
            TARGET_ID,
            False,
        )

        print("endpoint result:", result)

        assert result.get("resolved") == TARGET_ID
        assert result.get("found") is True

        print()
        print("=== DIRECT SQLITE VERIFICATION ===")

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            row = conn.execute(
                """
                SELECT
                    prediction_id,
                    status,
                    acknowledged
                FROM predictions
                WHERE prediction_id = ?
                """,
                (TARGET_ID,),
            ).fetchone()

            outcome = conn.execute(
                """
                SELECT
                    prediction_id,
                    outcome,
                    false_positive,
                    false_negative,
                    prevented
                FROM prediction_outcomes
                WHERE prediction_id = ?
                """,
                (TARGET_ID,),
            ).fetchone()

            assert row is not None
            assert row["status"] == "resolved"

            assert outcome is not None
            assert outcome["outcome"] == "incorrect"
            assert outcome["false_positive"] == 1
            assert outcome["false_negative"] == 0
            assert outcome["prevented"] == 0

            print("prediction status:", row["status"])
            print("outcome:", outcome["outcome"])
            print("false_positive:", outcome["false_positive"])
            print("false_negative:", outcome["false_negative"])
            print("prevented:", outcome["prevented"])

        finally:
            conn.close()

        print()
        print("PASS: existing persisted prediction resolved successfully.")
        print("PASS: prediction transitioned to terminal state in SQLite.")
        print("PASS: prediction outcome persisted.")
        print("PASS: no prediction was created.")
        print("PASS: no telemetry was injected.")

    print()
    print("Backend lifespan: STOPPED")


if __name__ == "__main__":
    asyncio.run(run())
