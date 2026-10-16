from pathlib import Path


def print_range(path, start, end):
    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    print(f"\n=== {path}:{start}-{end} ===")

    for number in range(start, min(end, len(lines)) + 1):
        print(f"{number}: {lines[number - 1]}")


def main():
    print("=== REAL FAILUREDNA BACKEND PIPELINE INSPECTION ===")
    print()
    print("READ-ONLY SOURCE INSPECTION.")
    print("No telemetry generated.")
    print("No prediction generated.")
    print("No state modified.")

    path = Path("backend/main.py")

    assert path.exists(), (
        "backend/main.py not found"
    )

    # Real telemetry ingestion + prediction path.
    print_range(
        path,
        470,
        610,
    )

    # Real prediction resolution endpoint/path.
    print_range(
        path,
        1490,
        1630,
    )

    # Real failure recording path.
    print_range(
        path,
        1680,
        1740,
    )

    print("\n=== RESULT ===")
    print("Production FailureDNA paths inspected.")
    print("No synthetic data generated.")
    print("No application state modified.")


if __name__ == "__main__":
    main()
