from pathlib import Path
import inspect

import backend.core.cognitive.failure_dna as failure_dna


def main():
    print("=== FAILURE-DNA IMPORT + EVENT ID PATCH DIAGNOSTIC ===")

    source = inspect.getsource(failure_dna)

    print("\n=== MODULE IMPORTS / UUID AVAILABILITY ===")

    for name in ["time", "uuid"]:
        print(f"{name} available:", hasattr(failure_dna, name))

    print("\n=== TOP OF failure_dna.py ===")

    lines = source.splitlines()

    for index, line in enumerate(lines[:45], 1):
        print(f"{index:03}: {line}")

    print("\n=== FAILURE EVENT DEFINITION ===")

    for index, line in enumerate(lines, 1):
        if "class FailureEvent" in line:
            start = max(0, index - 2)
            end = min(len(lines), index + 35)

            for n in range(start, end):
                print(f"{n + 1:03}: {lines[n]}")

            break

    print("\n=== record_failure() ID LINE ===")

    record_source = inspect.getsource(
        failure_dna.FailureDNAEngine.record_failure
    )

    for line in record_source.splitlines():
        if "event_id" in line:
            print(line)


if __name__ == "__main__":
    main()
