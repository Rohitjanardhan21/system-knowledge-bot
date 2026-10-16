from pathlib import Path

ROOT = Path.cwd()
TERMS = (
    ".execute(",
    "ActionExecutor(",
    "source=",
    "kill_process",
    "kill_high_cpu_process",
)

print("=== EXECUTOR CALL-SITE AUDIT ===")
print("READ-ONLY. NO PROCESS EXECUTION.")

for relative in (
    "backend",
    "agent.py",
    "app.py",
):
    base = ROOT / relative
    files = [base] if base.is_file() else (
        list(base.rglob("*.py")) if base.is_dir() else []
    )

    for path in sorted(files):
        try:
            lines = path.read_text(
                encoding="utf-8-sig",
                errors="replace",
            ).splitlines()
        except OSError:
            continue

        matches = [
            i for i, line in enumerate(lines)
            if any(term in line for term in TERMS)
        ]

        if not matches:
            continue

        print(f"\n--- {path.relative_to(ROOT)} ---")
        shown = set()
        for i in matches:
            for j in range(max(0, i - 3), min(len(lines), i + 4)):
                if j not in shown:
                    print(f"{j + 1:5}: {lines[j]}")
                    shown.add(j)
            print("    ...")

print("\n=== CALL-SITE AUDIT COMPLETE ===")
