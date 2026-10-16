from pathlib import Path

p = Path("judgment/test_end_to_end_failure_dna_crash_lifecycle.py")

print("=== TEST FILE VERIFICATION ===")
print("Path:", p.resolve())
print("Exists:", p.exists())
print("Size:", p.stat().st_size if p.exists() else "N/A")

if not p.exists():
    raise SystemExit("TEST FILE NOT FOUND")

source = p.read_text(encoding="utf-8")

print("\n=== CRASH TRAJECTORY SECTION ===")

lines = source.splitlines()

for i, line in enumerate(lines, 1):
    if "DETERMINISTIC CRASH" in line or "trajectory" in line.lower():
        start = max(1, i - 5)
        end = min(len(lines), i + 35)

        for n in range(start, end + 1):
            print(f"{n}: {lines[n - 1]}")

        break

print("\n=== OLD TRAJECTORY CHECK ===")

old_markers = [
    "progress = i / 11",
    "25.0 + progress * 5.0",
    "0.10 + progress * 0.05",
    'print("Prediction generated:"',
]

for marker in old_markers:
    print(marker, "FOUND" if marker in source else "not found")

print("\n=== NEW TRAJECTORY CHECK ===")

new_markers = [
    "trajectory = [",
    "(26.8, 0.30)",
    "(37.0, 1.30)",
    'candidate.failure_type == "CRASH"',
]

for marker in new_markers:
    print(marker, "FOUND" if marker in source else "not found")

print("\n=== RESULT ===")
if any(marker in source for marker in old_markers):
    print("OLD TEST CONTENT IS STILL ON DISK.")
elif all(marker in source for marker in new_markers):
    print("NEW TEST CONTENT IS ON DISK.")
else:
    print("TEST CONTENT DOES NOT MATCH EITHER EXPECTED VERSION.")
