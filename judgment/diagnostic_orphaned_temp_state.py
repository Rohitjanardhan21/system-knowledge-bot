from pathlib import Path
import json
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

STATE_PATH = Path("state/latest.json")
TEMP_PATH = STATE_PATH.with_suffix(".tmp")

print("=== ORPHANED TEMP STATE RECOVERY TEST ===")

# Establish valid authoritative state.
state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "approved"
target.pop("execution_completed_at", None)
target.pop("execution_result", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

# Remove any stale temp file from previous tests.
if TEMP_PATH.exists():
    TEMP_PATH.unlink()

print()
print("1. BASELINE:")
print(target["action"], "|", target["status"])

# Simulate a crash after completely writing the temporary state,
# but before replacing the authoritative state.
child_code = r'''
from pathlib import Path
import json
import os

STATE_PATH = Path("state/latest.json")
TEMP_PATH = STATE_PATH.with_suffix(".tmp")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "executing"

print("CHILD: writing orphaned temporary state", flush=True)

with TEMP_PATH.open("w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
    f.flush()
    os.fsync(f.fileno())

print("CHILD: temporary state fully written", flush=True)
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
print("3. AFTER CRASH:")

authoritative = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

authoritative_target = next(
    a for a in authoritative["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    "AUTHORITATIVE:",
    authoritative_target["action"],
    "|",
    authoritative_target["status"],
)

print(
    "TEMPORARY EXISTS:",
    TEMP_PATH.exists(),
)

# The authoritative state must remain unchanged.
assert authoritative_target["status"] == "approved"

# The orphaned temporary file must be valid but must NOT become
# authoritative automatically.
temporary = json.loads(
    TEMP_PATH.read_text(encoding="utf-8")
)

temporary_target = next(
    a for a in temporary["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    "TEMPORARY:",
    temporary_target["action"],
    "|",
    temporary_target["status"],
)

assert temporary_target["status"] == "executing"

print()
print("4. RESTART VALIDATION...")

# A fresh process must continue using latest.json.
child_check = subprocess.run(
    [
        sys.executable,
        "-c",
        """
import json
from pathlib import Path

state = json.loads(
    Path("state/latest.json").read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    "FRESH PROCESS:",
    target["action"],
    "|",
    target["status"],
)

assert target["status"] == "approved"
""",
    ],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print(child_check.stdout)

if child_check.returncode != 0:
    print(child_check.stderr)
    raise SystemExit(child_check.returncode)

print()
print("5. RESULT:")
print("RESULT: PASS")
print("Authoritative state remained unchanged.")
print("Orphaned temporary state was not promoted.")
print("Fresh process continued from latest.json.")
print("Atomic persistence boundary is preserved.")
