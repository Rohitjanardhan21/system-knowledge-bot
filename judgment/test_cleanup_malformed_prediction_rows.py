import sqlite3
from pathlib import Path

DB_PATH = Path("data") / "cvis.db"

TARGET_IDS = {
    "pred_ack_durability_regression_unique",
    "pred_outcome_durability_regression_unique",
    "pred_outcome_conflict_regression_unique",
    "pred_outcome_idempotency_regression_unique",
}

EXPECTED_ISO_CREATED = "2026-10-08T10:00:00+00:00"
EXPECTED_ISO_EXPECTED = "2026-10-08T10:30:00+00:00"


def main():
    print("=== TARGETED PREDICTION DB CLEANUP ===")
    print()
    print("Purpose: remove only four malformed regression-test rows.")
    print("No telemetry generated.")
    print("No predictions generated.")
    print("No production code modified.")
    print()

    if not DB_PATH.exists():
        raise AssertionError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        placeholders = ",".join("?" for _ in TARGET_IDS)

        rows = conn.execute(
            f"""
            SELECT prediction_id, created_at, expected_at, status
            FROM predictions
            WHERE prediction_id IN ({placeholders})
            """,
            tuple(TARGET_IDS),
        ).fetchall()

        print("Target rows found:", len(rows))

        found_ids = {row["prediction_id"] for row in rows}

        if found_ids != TARGET_IDS:
            missing = TARGET_IDS - found_ids
            extra = found_ids - TARGET_IDS
            raise AssertionError(
                f"Unexpected target set. Missing={missing}, Extra={extra}"
            )

        for row in rows:
            print(
                f'{row["prediction_id"]}: '
                f'created_at={row["created_at"]!r}, '
                f'expected_at={row["expected_at"]!r}, '
                f'status={row["status"]!r}'
            )

            assert row["created_at"] == EXPECTED_ISO_CREATED, (
                f'Unexpected created_at for {row["prediction_id"]}'
            )
            assert row["expected_at"] == EXPECTED_ISO_EXPECTED, (
                f'Unexpected expected_at for {row["prediction_id"]}'
            )

        print()
        print("All four rows match the known malformed regression-test data.")
        print("Deleting exactly these four rows...")

        conn.execute("BEGIN")

        conn.execute(
            f"""
            DELETE FROM predictions
            WHERE prediction_id IN ({placeholders})
            """,
            tuple(TARGET_IDS),
        )

        deleted = conn.execute("SELECT changes()").fetchone()[0]

        assert deleted == 4, (
            f"Expected exactly 4 deletions, got {deleted}"
        )

        conn.commit()

        remaining = conn.execute(
            f"""
            SELECT prediction_id
            FROM predictions
            WHERE prediction_id IN ({placeholders})
            """,
            tuple(TARGET_IDS),
        ).fetchall()

        assert not remaining, (
            f"Target rows still present: {[r['prediction_id'] for r in remaining]}"
        )

        print()
        print("Deleted rows:", deleted)
        print("Remaining targeted rows:", len(remaining))
        print()
        print("PASS: only the four malformed regression-test rows were removed.")
        print("The predictions table and production application code were not modified.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
