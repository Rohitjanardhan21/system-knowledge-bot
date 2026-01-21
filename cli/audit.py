from pathlib import Path

AUDIT_DIR = Path("bot_audit")
DECISIONS = AUDIT_DIR / "decisions.log"
SHADOW = AUDIT_DIR / "shadow.log"

def _print_log(path: Path, title: str, limit: int):
    print(f"\n{title}:\n")

    if not path.exists():
        print("(no entries)")
        return

    with open(path, "r") as f:
        lines = f.readlines()

    for line in lines[-limit:]:
        print(line.strip())

def show_audit(limit=20):
    _print_log(DECISIONS, "Recent surfaced decisions", limit)
    _print_log(SHADOW, "Recent suppressed decisions", limit)
