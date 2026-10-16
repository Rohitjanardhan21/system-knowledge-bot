import asyncio

from backend.main import app
from backend.core.cognitive.failure_dna import get_dna_engine
from backend.core.storage.db import load_active_predictions


async def run():
    print("=== REAL PREDICTION RESTORE REGISTRY DIAGNOSTIC ===")
    print()
    print("READ-ONLY TEST")
    print("No prediction creation.")
    print("No telemetry injection.")
    print("No database modification.")
    print()

    dna = get_dna_engine()

    async with app.router.lifespan_context(app):
        print("Backend lifespan: STARTED")
        print()

        db_rows = await load_active_predictions()

        print("=== SQLITE ACTIVE PREDICTIONS ===")
        print("SQLite active-row count:", len(db_rows))

        for row in db_rows:
            print(
                "DB:",
                row.get("prediction_id"),
                "| type=",
                row.get("failure_type"),
                "| status=",
                row.get("status"),
                "| created_at=",
                repr(row.get("created_at")),
                "| expected_at=",
                repr(row.get("expected_at")),
                "| acknowledged=",
                row.get("acknowledged"),
            )

        print()
        print("=== FAILUREDNA IN-MEMORY REGISTRY ===")

        registry = dna._active_predictions

        print("FailureDNA registry count:", len(registry))

        for pred_id, pred in registry.items():
            print(
                "DNA:",
                pred_id,
                "| type=",
                pred.failure_type,
                "| acknowledged=",
                pred.acknowledged,
                "| resolved=",
                pred.resolved,
            )

        print()
        print("=== REGISTRY COMPARISON ===")

        db_ids = {
            row.get("prediction_id")
            for row in db_rows
            if row.get("prediction_id")
        }

        dna_ids = set(registry.keys())

        only_db = db_ids - dna_ids
        only_dna = dna_ids - db_ids
        intersection = db_ids & dna_ids

        print("IDs in SQLite only:", len(only_db))
        for pred_id in sorted(only_db):
            print("  SQLITE_ONLY:", pred_id)

        print("IDs in FailureDNA only:", len(only_dna))
        for pred_id in sorted(only_dna):
            print("  DNA_ONLY:", pred_id)

        print("IDs present in both:", len(intersection))
        for pred_id in sorted(intersection):
            print("  BOTH:", pred_id)

        print()
        print("=== PRODUCTION VIEW ===")

        dna_active = dna.get_active_predictions()

        print(
            "FailureDNA get_active_predictions():",
            len(dna_active),
        )

        for pred in dna_active:
            print(
                pred.prediction_id,
                "|",
                pred.failure_type,
                "| resolved=",
                pred.resolved,
            )

        print()
        print("=== RESULT ===")

        if db_ids and not dna_ids:
            print(
                "FINDING: active predictions exist durably in SQLite "
                "but are absent from FailureDNA's in-memory registry."
            )
            print(
                "This is a restart-restoration synchronization gap, "
                "not a telemetry problem."
            )

        elif only_db:
            print(
                "FINDING: some SQLite predictions are not represented "
                "in FailureDNA memory."
            )

        elif not db_ids and not dna_ids:
            print(
                "FINDING: no active predictions exist in either store."
            )

        else:
            print(
                "FINDING: SQLite and FailureDNA active prediction "
                "registries are aligned."
            )

        print()
        print("PASS: diagnostic completed without modifying state.")

    print()
    print("Backend lifespan: STOPPED")


if __name__ == "__main__":
    asyncio.run(run())
