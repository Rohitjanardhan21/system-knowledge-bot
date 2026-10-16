from pathlib import Path


ROOTS = [
    Path("backend"),
    Path("judgment"),
]


TARGETS = (
    "FailureDNAEngine(",
    ".ingest(",
    ".predict(",
    ".record_failure(",
    ".resolve_prediction(",
    "record_failure(",
    "resolve_prediction(",
)


def main():
    print("=== REAL FAILUREDNA PRODUCTION PIPELINE DISCOVERY ===")
    print()
    print("This diagnostic does NOT create predictions.")
    print("It does NOT inject telemetry.")
    print("It does NOT modify application state.")
    print("It only discovers the real production call sites.")
    print()

    found = []

    for root in ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue

            try:
                text = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                continue

            lines = text.splitlines()

            for number, line in enumerate(lines, 1):
                stripped = line.strip()

                if not stripped:
                    continue

                if stripped.startswith("#"):
                    continue

                matched = [
                    target
                    for target in TARGETS
                    if target in line
                ]

                if matched:
                    found.append(
                        (
                            str(path),
                            number,
                            matched,
                            stripped,
                        )
                    )

    print("PRODUCTION CALL SITES FOUND:", len(found))
    print()

    for path, number, matched, line in found:
        print(f"{path}:{number}")
        print("  matches:", ", ".join(matched))
        print("  code:", line)
        print()

    print("=== CLASSIFICATION ===")

    production_candidates = []

    for path, number, matched, line in found:
        lower_path = path.lower()

        # Test files are intentionally separated from production candidates.
        if (
            "\\test_" in lower_path
            or "/test_" in lower_path
            or lower_path.startswith("judgment\\test")
            or lower_path.startswith("judgment/test")
        ):
            continue

        production_candidates.append(
            (path, number, matched, line)
        )

    print(
        "Non-test call sites:",
        len(production_candidates),
    )

    for path, number, matched, line in production_candidates:
        print(
            f"REAL CANDIDATE -> {path}:{number} "
            f"| {', '.join(matched)}"
        )

    print()
    print("RESULT: DISCOVERY COMPLETE.")
    print(
        "No synthetic telemetry or prediction was generated."
    )


if __name__ == "__main__":
    main()
