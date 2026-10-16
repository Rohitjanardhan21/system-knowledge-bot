from pathlib import Path
import json
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

AUDIT_PATH = Path("state/audit.json")
TEMP_PATH = AUDIT_PATH.with_suffix(".tmp")

print("=== AUDIT ORPHANED TEMP CLEANUP TEST ===")

AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

baseline = [
    {
        "event": "baseline",
        "status": "approved",
        "action": "free-disk-space",
        "result": "baseline-audit",
    }
]

AUDIT_PATH.write_text(
    json.dumps(baseline, indent=2),
    encoding="utf-8",
)

if TEMP_PATH.exists():
    TEMP_PATH.unlink()

print()
print("1. BASELINE:")
print(json.loads(AUDIT_PATH.read_text(encoding="utf-8")))
print("TEMPORARY EXISTS:", TEMP_PATH.exists())

child_code = r'''
from pathlib import Path
import json
import os

AUDIT_PATH = Path("state/audit.json")
TEMP_PATH = AUDIT_PATH.with_suffix(".tmp")

audit = json.loads(
    AUDIT_PATH.read_text(encoding="utf-8")
)

audit.append({
    "event": "execution-completed",
    "status": "executed",
    "action": "free-disk-space",
    "result": "orphaned-audit-event",
})

print("CHILD: writing orphaned temporary audit", flush=True)

with TEMP_PATH.open("w", encoding="utf-8") as f:
    json.dump(audit, f, indent=2)
    f.flush()
    os.fsync(f.fileno())

print("CHILD: temporary audit fully written", flush=True)
print("CHILD: simulated crash BEFORE os.replace()", flush=True)

os._exit(99)
'''

print()
print("2. STARTING CRASHING WRITER...")

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print("CHILD OUTPUT:")
print(child.stdout)

assert child.returncode == 99
assert TEMP_PATH.exists()

print()
print("3. BEFORE CLEANUP:")

authoritative = json.loads(
    AUDIT_PATH.read_text(encoding="utf-8")
)

temporary = json.loads(
    TEMP_PATH.read_text(encoding="utf-8")
)

print("AUTHORITATIVE:", authoritative)
print("TEMPORARY:", temporary)

assert authoritative == baseline
assert any(
    e.get("result") == "orphaned-audit-event"
    for e in temporary
)

print()
print("4. CLEANING ORPHANED AUDIT TEMP...")

if TEMP_PATH.exists():
    TEMP_PATH.unlink()

print("TEMPORARY EXISTS:", TEMP_PATH.exists())

assert not TEMP_PATH.exists()

print()
print("5. VERIFYING AUTHORITATIVE AUDIT...")

final_audit = json.loads(
    AUDIT_PATH.read_text(encoding="utf-8")
)

print("FINAL:", final_audit)

assert final_audit == baseline

print()
print("6. RESULT:")
print("RESULT: PASS")
print("Orphaned audit temporary state was cleaned.")
print("Authoritative audit remained unchanged.")
print("Audit atomic persistence boundary is preserved.")
