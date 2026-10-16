from pathlib import Path

ROOT = Path.cwd()
TARGETS = (
    ("backend/core/actions/action_executor.py", (
        "ACTIONS", "def execute_action", "kill_process",
        "kill_high_cpu", "terminate", "subprocess",
    )),
    ("backend/core/actions/auto_remediation.py", (
        "execute_action", "action_id", "source=", "kill",
    )),
    ("agent.py", (
        "command_type == \"kill_high_cpu\"", "confirm",
        "proc.terminate", "create_time",
    )),
    ("backend/intelligence_pipeline.py", (
        "executor.execute", "auto_execute", "executable",
    )),
)

print("=== DESTRUCTIVE ACTION PATH AUDIT ===")
print("READ-ONLY. NO PROCESS EXECUTION.")

for relative, terms in TARGETS:
    path = ROOT / relative
    if not path.is_file():
        print(f"\n[MISSING FILE] {relative}")
        continue

    lines = path.read_text(
        encoding="utf-8-sig", errors="replace"
    ).splitlines()

    matches = [
        i for i, line in enumerate(lines)
        if any(term.lower() in line.lower() for term in terms)
    ]

    print(f"\n--- {relative} ({len(lines)} lines) ---")
    shown = set()

    for i in matches:
        start = max(0, i - 5)
        end = min(len(lines), i + 9)

        for j in range(start, end):
            if j not in shown:
                print(f"{j + 1:5}: {lines[j]}")
                shown.add(j)

        print("    ...")

print("\n=== AUDIT COMPLETE ===")
