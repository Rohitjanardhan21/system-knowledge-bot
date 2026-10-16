from pathlib import Path

print("=== PROCESS TERMINATION AUTHORITY INSPECTION ===")
print("READ-ONLY SOURCE INSPECTION.")
print("NO SYNTHETIC TELEMETRY.")
print("NO DATABASE CHANGES.")
print()

targets = [
    Path("agent.py"),
    Path("backend/main.py"),
    Path("backend/core/actions/action_executor.py"),
    Path("backend/core/actions/auto_remediation.py"),
    Path("backend/core/cognitive/failure_dna.py"),
]

terms = [
    "kill_high_cpu",
    "kill_process",
    "terminate",
    "expected",
    "create_time",
    "verified_exit",
    "already_exited",
    "record_execution",
    "PROCESS_CRASH",
]

for path in targets:
    if not path.exists():
        print(f"\n--- {path} ---")
        print("NOT FOUND")
        continue

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    print(f"\n--- {path} ---")

    found = False

    for i, line in enumerate(lines, start=1):
        lower = line.lower()

        if any(term.lower() in lower for term in terms):
            found = True

            start = max(1, i - 3)
            end = min(len(lines), i + 4)

            print(f"\n[{start}-{end}]")
            for n in range(start, end + 1):
                print(f"{n:5}: {lines[n-1]}")

    if not found:
        print("No matching lifecycle/termination terms found.")

print("\n=== INSPECTION COMPLETE ===")
