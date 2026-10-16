from pathlib import Path


def find_terms(path, terms):
    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    print(f"=== {path} ===")

    for number, line in enumerate(lines, 1):
        if any(term in line for term in terms):
            start = max(1, number - 8)
            end = min(len(lines), number + 15)

            print()
            print(f"--- lines {start}-{end} ---")

            for n in range(start, end + 1):
                print(f"{n}: {lines[n - 1]}")


def main():
    print("=== REAL TELEMETRY COLLECTION PATH INSPECTION ===")
    print()
    print("READ-ONLY SOURCE INSPECTION.")
    print("No synthetic telemetry.")
    print("No prediction generated.")
    print("No state modified.")

    path = Path("backend/main.py")

    assert path.exists(), (
        "backend/main.py not found"
    )

    find_terms(
        path,
        [
            "def _build_feature_vector",
            "def start_collector",
            "def stop_collector",
            "_collector_thread",
            "_collector_stop",
            "_collect(",
            "psutil",
        ],
    )

    print()
    print("=== RESULT ===")
    print("Actual production telemetry construction/startup paths inspected.")
    print("No synthetic data generated.")
    print("No application state modified.")


if __name__ == "__main__":
    main()
