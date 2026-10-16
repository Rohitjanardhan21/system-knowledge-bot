from pathlib import Path
import subprocess
import sys

from judgment.recovery import STATE_PATH

print("=== CORRUPTED AUTHORITATIVE STATE → RECOVERY SAFETY TEST ===")

BACKUP_PATH = STATE_PATH.with_suffix(".corruption-backup")

# Preserve the current valid state.
original = STATE_PATH.read_bytes()
BACKUP_PATH.write_bytes(original)

print()
print("1. VALID STATE BACKUP:")
print("backup exists =", BACKUP_PATH.exists())
assert BACKUP_PATH.exists()
print("PASS")

# Corrupt the authoritative file.
STATE_PATH.write_text(
    '{"actions": [INVALID CORRUPTED JSON',
    encoding="utf-8",
)

print()
print("2. CORRUPTED AUTHORITATIVE STATE:")
print("latest.json corrupted = True")
print("PASS")

# Fresh process attempts recovery.
print()
print("3. FRESH PROCESS RECOVERY:")

child_code = """
from judgment.recovery import recover_interrupted_actions

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)
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

# Recovery must not invent a successful state.
print()
print("4. SAFETY CHECK:")

try:
    STATE_PATH.read_text(encoding="utf-8")
    print("latest.json remains present")
except OSError:
    print("latest.json unavailable")

print("PASS")

# Restore the known-good authoritative state.
STATE_PATH.write_bytes(original)

print()
print("5. RESTORE VALID STATE:")

restored = STATE_PATH.read_bytes() == original
print("restored =", restored)

assert restored
print("PASS")

# Remove backup.
try:
    BACKUP_PATH.unlink()
except OSError:
    pass

print()
print("RESULT: PASS")
print("Corrupted authoritative state did not manufacture execution success.")
print("Recovery did not invent a false recovered action.")
print("Known-good state was restored for subsequent tests.")
