import json
from pathlib import Path
import subprocess
import sys

from judgment.audit import AUDIT_PATH, AUDIT_TEMP_PATH, load_audit

print("=== ORPHANED AUDIT TEMP → RESTART RECOVERY TEST ===")

# Ensure the authoritative audit file exists.
AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

if not AUDIT_PATH.exists():
    AUDIT_PATH.write_text("[]", encoding="utf-8")

audit_before = load_audit()

print()
print("1. AUTHORITATIVE AUDIT:")
print("entries =", len(audit_before))
print("PASS")

# Simulate a crash during an audit atomic replacement by creating
# an orphaned temporary audit file containing a fake event.
fake_audit = list(audit_before)

fake_audit.append({
    "timestamp": "2099-01-01T00:00:00+00:00",
    "event": "execution-completed",
    "action": "free-disk-space",
    "status": "executed",
    "result": "orphaned-fake-success",
})

AUDIT_TEMP_PATH.write_text(
    json.dumps(fake_audit, indent=2),
    encoding="utf-8",
)

print()
print("2. ORPHANED AUDIT TEMP:")
print(
    AUDIT_TEMP_PATH,
    "| exists =",
    AUDIT_TEMP_PATH.exists(),
)

assert AUDIT_TEMP_PATH.exists()
print("PASS")

# Fresh process performs audit cleanup.
print()
print("3. FRESH PROCESS AUDIT RECOVERY:")

child_code = """
from judgment.audit import cleanup_audit_temp, load_audit

before = load_audit()
cleanup_audit_temp()
after = load_audit()

print("AUDIT ENTRIES BEFORE:", len(before))
print("AUDIT ENTRIES AFTER:", len(after))

assert len(after) == len(before)
"""

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print(child.stdout)

if child.returncode != 0:
    print(child.stderr)
    raise SystemExit(child.returncode)

print("PASS")

# The authoritative audit must remain unchanged.
audit_after = load_audit()

print()
print("4. AUTHORITATIVE AUDIT AFTER RECOVERY:")
print("entries =", len(audit_after))

assert len(audit_after) == len(audit_before)

fake_matches = [
    event
    for event in audit_after
    if event.get("result") == "orphaned-fake-success"
]

assert not fake_matches

print("PASS")

print()
print("5. TEMP FILE CLEANUP:")
print("exists =", AUDIT_TEMP_PATH.exists())

assert not AUDIT_TEMP_PATH.exists()

print("PASS")

print()
print("RESULT: PASS")
print("Orphaned audit temporary state was detected.")
print("Authoritative audit.json remained unchanged.")
print("Fake successful audit state was not adopted.")
print("Orphaned audit temporary state was cleaned after restart.")
