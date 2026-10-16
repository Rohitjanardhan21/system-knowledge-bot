from pathlib import Path

terms = (
    "approval",
    "approved",
    "approval_id",
    "require_scope",
    "principal",
    "requested_by",
    "get_redis",
    "redis_url",
    "JWT_SECRET",
    "API_KEY",
)

files = [
    Path("backend/main.py"),
    Path("backend/core/devices/command_service.py"),
    Path("backend/auth.py"),
    Path("backend/security.py"),
    Path("backend/policy_engine.py"),
    Path("backend/action_executor.py"),
]

print("=== APPROVAL AND IDENTITY INFRASTRUCTURE AUDIT ===")
print("READ-ONLY. NO NETWORK OR PROCESS EXECUTION.")

for path in files:
    if not path.is_file():
        continue

    lines = path.read_text(
        encoding="utf-8-sig", errors="replace"
    ).splitlines()

    matches = [
        i for i, line in enumerate(lines)
        if any(term.lower() in line.lower() for term in terms)
    ]

    if not matches:
        continue

    print(f"\n--- {path} ({len(lines)} lines) ---")
    shown = set()

    for i in matches:
        start = max(0, i - 3)
        end = min(len(lines), i + 5)

        for j in range(start, end):
            if j not in shown:
                print(f"{j + 1:5}: {lines[j]}")
                shown.add(j)

        print("    ...")

print("\n=== AUDIT COMPLETE ===")
