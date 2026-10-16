from pathlib import Path

ROOT = Path.cwd()

FILES = [
    "agent.py",
    "backend/action_executor.py",
    "backend/policy_engine.py",
    "backend/decision_engine_v2.py",
    "backend/main.py",
    "backend/core/process_lifecycle.py",
]

TERMS = (
    "terminate(",
    "kill_process_by_name",
    "kill_high_cpu",
    "auto_execute",
    "requires_confirmation",
    "approval",
    "allowlist",
    "policy",
    "mark_expected_termination",
    "clear_expected_termination",
)

print("=== AUTHORIZATION POLICY SOURCE AUDIT ===")
print("Repository:", ROOT)
print("READ-ONLY: no source modifications or process termination.")

for relative in FILES:
    path = ROOT / relative
    print(f"\n{'=' * 72}\nFILE: {relative}")

    if not path.is_file():
        print("NOT FOUND")
        continue

    lines = path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).splitlines()

    matches = [
        (index, line)
        for index, line in enumerate(lines, start=1)
        if any(term in line.lower() for term in TERMS)
    ]

    if not matches:
        print("No matching enforcement terms found.")
        continue

    for index, line in matches:
        print(f"{index:5}: {line.rstrip()}")

print("\n=== AUDIT COMPLETE ===")
print("Use the actual source and test results before implementing changes.")
