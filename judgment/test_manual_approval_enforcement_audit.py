from pathlib import Path

ROOT = Path.cwd()

RANGES = {
    "backend/action_executor.py": [(1, 80), (160, 270), (440, 510), (510, 750)],
    "agent.py": [(680, 745), (820, 890)],
    "backend/decision_engine_v2.py": [(295, 380)],
}

print("=== MANUAL-APPROVAL ENFORCEMENT AUDIT ===")
print("READ-ONLY. NO PROCESS TERMINATION.")

for filename, ranges in RANGES.items():
    path = ROOT / filename
    print(f"\n{'=' * 76}\nFILE: {filename}")

    if not path.is_file():
        print("FILE NOT FOUND")
        continue

    lines = path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).splitlines()

    for start, end in ranges:
        print(f"\n--- Lines {start}-{min(end, len(lines))} ---")
        for index in range(start - 1, min(end, len(lines))):
            print(f"{index + 1:5}: {lines[index]}")

print("\n=== AUDIT COMPLETE ===")
