import os
from pathlib import Path

root = Path(".")
needle = "kill_high_cpu"
excluded_directories = {".venv", "__pycache__", ".git"}


def python_files():
    for current_root, directories, filenames in os.walk(root):
        invalid_windows_names = [
            name for name in directories if name.endswith(".")
        ]
        for name in invalid_windows_names:
            print(
                "SKIPPING WINDOWS-INCOMPATIBLE DIRECTORY:",
                Path(current_root) / name,
            )

        directories[:] = [
            name
            for name in directories
            if name not in excluded_directories and not name.endswith(".")
        ]

        for filename in filenames:
            if filename.endswith(".py"):
                yield Path(current_root) / filename

print("=== REAL TERMINATION AUTHORITY SOURCE DISCOVERY ===")
print("READ-ONLY.")
print("NO PROCESS TERMINATION.")
print("NO SYNTHETIC TELEMETRY.")
print("NO FAILUREDNA.")
print("NO DATABASE CHANGES.")

matches = []

for path in python_files():
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue

    if needle not in text:
        continue

    for line_no, line in enumerate(text.splitlines(), 1):
        if needle in line:
            matches.append((str(path), line_no, line.strip()))

print("\n1. ALL PROJECT REFERENCES TO kill_high_cpu")
print("   matches:", len(matches))

for path, line_no, line in matches:
    print(f"   {path}:{line_no}: {line}")

print("\n2. LIKELY DESTRUCTIVE IMPLEMENTATIONS")

implementation_markers = (
    "proc.terminate(",
    ".terminate()",
    "Process remediation",
    "Destructive process termination",
)

found = []

for path in python_files():
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        continue

    for i, line in enumerate(lines):
        if any(marker in line for marker in implementation_markers):
            found.append((str(path), i + 1, line.strip()))

for path, line_no, line in found:
    print(f"   {path}:{line_no}: {line}")

print("\n3. RESULT")

if not matches:
    print("NO kill_high_cpu IMPLEMENTATION FOUND.")
    raise SystemExit(1)

print(
    "SOURCE LOCATIONS IDENTIFIED."
    " NO DESTRUCTIVE CALL WAS EXECUTED."
)
print("RESULT: PASS")
