from pathlib import Path


def print_matches(path, terms):
    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    print(f"\n=== {path} ===")

    for number, line in enumerate(lines, 1):
        if any(term in line for term in terms):
            start = max(1, number - 10)
            end = min(len(lines), number + 20)

            print(f"\n--- lines {start}-{end} ---")

            for n in range(start, end + 1):
                print(f"{n}: {lines[n - 1]}")


def main():
    print("=== REAL PREDICTION TIMESTAMP WRITE-PATH INSPECTION ===")
    print()
    print("READ-ONLY SOURCE INSPECTION.")
    print("No synthetic prediction.")
    print("No database modification.")
    print("No rows changed.")

    db_path = Path("backend/core/storage/db.py")
    assert db_path.exists(), "backend/core/storage/db.py not found"

    print_matches(
        db_path,
        [
            "def save_prediction",
            "async def save_prediction",
            "INSERT INTO predictions",
            "created_at",
            "expected_at",
            "lead_time_seconds",
        ],
    )

    print()
    print("=== SEARCHING PROJECT FOR THE AFFECTED PREDICTION IDS ===")

    targets = [
        "pred_ack_durability_regression_unique",
        "pred_outcome_durability_regression_unique",
        "pred_outcome_conflict_regression_unique",
        "pred_outcome_idempotency_regression_unique",
    ]

    for root in (
        Path("judgment"),
        Path("backend"),
    ):
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            try:
                text = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                continue

            matched = [
                target
                for target in targets
                if target in text
            ]

            if matched:
                print()
                print(f"{path}")
                print("matched:", ", ".join(matched))

                lines = text.splitlines()

                for number, line in enumerate(lines, 1):
                    if any(target in line for target in matched):
                        start = max(1, number - 8)
                        end = min(len(lines), number + 15)

                        print(
                            f"--- lines {start}-{end} ---"
                        )

                        for n in range(start, end + 1):
                            print(f"{n}: {lines[n - 1]}")

    print()
    print("=== RESULT ===")
    print("Prediction timestamp write paths inspected.")
    print("No synthetic data generated.")
    print("No database state modified.")


if __name__ == "__main__":
    main()
