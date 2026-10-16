from pathlib import Path

ROOT = Path.cwd()

TARGETS = {
    "agent.py": [
        "if command_type == \"kill_high_cpu\":",
        "proc.terminate()",
    ],
    "backend/action_executor.py": [
        "def execute(",
        "def _execute_action(",
        "def kill_process_by_name(",
        "proc.terminate()",
        "mark_expected_termination(",
    ],
    "backend/policy_engine.py": [
        "def is_action_allowed(",
        "def get_best_action(",
    ],
    "backend/decision_engine_v2.py": [
        "auto_execute = (",
        "requires_confirmation",
        "def _build_decision(",
    ],
    "backend/core/process_lifecycle.py": [
        "def mark_expected_termination(",
        "def clear_expected_termination(",
    ],
}

print("=== AUTHORIZATION ENFORCEMENT CONTEXT ===")
print("READ-ONLY SOURCE INSPECTION")
print("No process execution or termination.")

for relative, anchors in TARGETS.items():
    path = ROOT / relative
    print(f"\n{'=' * 78}\nFILE: {relative}")

    if not path.is_file():
        print("FILE NOT FOUND")
        continue

    lines = path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).splitlines()

    selected = set()

    for anchor in anchors:
        matches = [
            i for i, line in enumerate(lines)
            if anchor in line
        ]

        if not matches:
            print(f"\nANCHOR NOT FOUND: {anchor}")
            continue

        for index in matches:
            start = max(0, index - 12)
            end = min(len(lines), index + 24)
            selected.update(range(start, end))

    previous = -2

    for index in sorted(selected):
        if index > previous + 1:
            print("\n    ...")
        print(f"{index + 1:5}: {lines[index]}")
        previous = index

print("\n=== INSPECTION COMPLETE ===")
