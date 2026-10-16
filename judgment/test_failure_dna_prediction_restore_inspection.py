from pathlib import Path
import sqlite3


def print_range(path, start, end):
    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    print(f"\n=== {path}:{start}-{end} ===")

    for number in range(start, min(end, len(lines)) + 1):
        print(f"{number}: {lines[number - 1]}")


def main():
    print("=== REAL PREDICTION RESTORE FAILURE INSPECTION ===")
    print()
    print("READ-ONLY INSPECTION.")
    print("No synthetic prediction.")
    print("No database modification.")
    print("No rows deleted or repaired.")

    main_path = Path("backend/main.py")
    db_path = Path("data/cvis.db")

    assert main_path.exists(), "backend/main.py not found"
    assert db_path.exists(), f"Database not found: {db_path}"

    # The startup warning occurred while restoring cognitive predictions.
    print_range(main_path, 730, 780)

    print()
    print("=== PREDICTIONS TABLE SCHEMA ===")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        columns = conn.execute(
            "PRAGMA table_info(predictions)"
        ).fetchall()

        for row in columns:
            print(
                f"{row['name']} | "
                f"type={row['type']} | "
                f"notnull={row['notnull']} | "
                f"default={row['dflt_value']}"
            )

        print()
        print("=== AFFECTED REAL PREDICTION ROWS ===")

        ids = [
            "pred_ack_durability_regression_unique",
            "pred_outcome_durability_regression_unique",
            "pred_outcome_conflict_regression_unique",
            "pred_outcome_idempotency_regression_unique",
        ]

        placeholders = ",".join("?" for _ in ids)

        rows = conn.execute(
            f"""
            SELECT *
            FROM predictions
            WHERE prediction_id IN ({placeholders})
            ORDER BY prediction_id
            """,
            ids,
        ).fetchall()

        print("rows found:", len(rows))

        for row in rows:
            print()
            print(dict(row))

    finally:
        conn.close()

    print()
    print("=== RESULT ===")
    print("Restore implementation and affected persisted rows inspected.")
    print("No synthetic data generated.")
    print("No database state modified.")


if __name__ == "__main__":
    main()
