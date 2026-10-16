from pathlib import Path

targets = {
    "backend/core/auth/auth.py": [
        "async def get_redis",
        "def get_redis",
        "aioredis.from_url",
        "REDIS_OK",
    ],
    "backend/action_executor.py": [
        "class ActionExecutor",
        "def execute(",
        "def _execute_action",
    ],
    "backend/core/actions/action_executor.py": [
        "def execute_action(",
        "AUTONOMOUS_ALLOWED_ACTIONS",
    ],
}

print("=== APPROVAL STORAGE COMPATIBILITY AUDIT ===")
print("READ-ONLY. NO REDIS CONNECTION OR PROCESS EXECUTION.")

for filename, terms in targets.items():
    path = Path(filename)
    print(f"\n--- {filename} ---")

    if not path.is_file():
        print("FILE NOT FOUND")
        continue

    lines = path.read_text(
        encoding="utf-8-sig", errors="replace"
    ).splitlines()

    for term in terms:
        matches = [
            i for i, line in enumerate(lines)
            if term.lower() in line.lower()
        ]
        if not matches:
            print(f"\n[NOT FOUND] {term}")
            continue

        for i in matches[:2]:
            print(f"\n[{term}, line {i + 1}]")
            for j in range(max(0, i - 3), min(len(lines), i + 9)):
                print(f"{j + 1:5}: {lines[j]}")

print("\n=== AUDIT COMPLETE ===")
