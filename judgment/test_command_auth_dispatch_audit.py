import ast
from pathlib import Path

targets = {
    "backend/core/devices/command_service.py": (
        "ALLOWED_COMMANDS",
        "def _validate_command_type",
        "async def",
        "command_type",
        "payload",
        "device_id",
        "user_id",
        "auth",
        "signature",
        "execute",
    ),
    "backend/main.py": (
        "command_type: str",
        "command_service",
        "execute_device_command",
        "command_id",
        "user_id",
        "authorization",
        "Depends(",
    ),
}

print("=== COMMAND AUTHENTICATION / DISPATCH AUDIT ===")
print("READ-ONLY. NO PROCESS EXECUTION.")

for filename, terms in targets.items():
    path = Path(filename)
    if not path.is_file():
        print(f"\n[MISSING] {filename}")
        continue

    lines = path.read_text(
        encoding="utf-8-sig", errors="replace"
    ).splitlines()

    print(f"\n--- {filename} ({len(lines)} lines) ---")
    matches = [
        i for i, line in enumerate(lines)
        if any(term.lower() in line.lower() for term in terms)
    ]

    shown = set()
    for i in matches:
        start = max(0, i - 4)
        end = min(len(lines), i + 7)
        for j in range(start, end):
            if j not in shown:
                print(f"{j + 1:5}: {lines[j]}")
                shown.add(j)
        print("    ...")

print("\n=== AUDIT COMPLETE ===")
