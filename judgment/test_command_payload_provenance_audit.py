from pathlib import Path

checks = {
    "backend/core/devices/command_service.py": [
        "ALLOWED_COMMANDS",
        "def _validate_command_type",
        "async def create_command",
    ],
    "backend/main.py": [
        "class DeviceCommandCreatePayload",
        "async def create_device_command",
        "async def poll_device_commands",
    ],
    "agent.py": [
        "def execute_device_command",
        'command_type == "kill_high_cpu"',
        'payload.get("confirm"',
        "execute_device_command(",
        "command.get(",
    ],
}

print("=== COMMAND ALLOWLIST AND PAYLOAD-PROVENANCE AUDIT ===")
print("READ-ONLY. NO COMMANDS OR PROCESSES EXECUTED.")

for filename, terms in checks.items():
    path = Path(filename)
    print(f"\n--- {filename} ---")

    if not path.is_file():
        print("FILE NOT FOUND")
        continue

    lines = path.read_text(
        encoding="utf-8-sig", errors="replace"
    ).splitlines()

    shown_ranges = []
    for term in terms:
        matches = [
            i for i, line in enumerate(lines)
            if term.lower() in line.lower()
        ]
        if not matches:
            print(f"\n[NOT FOUND] {term}")
            continue

        for i in matches:
            start = max(0, i - 5)
            end = min(len(lines), i + 10)

            if any(start < old_end and end > old_start
                   for old_start, old_end in shown_ranges):
                continue

            shown_ranges.append((start, end))
            print(f"\n[SEARCH: {term}]")
            for j in range(start, end):
                print(f"{j + 1:5}: {lines[j]}")

print("\n=== AUDIT COMPLETE ===")
