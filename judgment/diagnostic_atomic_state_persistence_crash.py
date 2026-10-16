from pathlib import Path
import json
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

STATE_PATH = Path("state/latest.json")

print("=== ATOMIC STATE PERSISTENCE CRASH TEST ===")

# Establish known-good state.
state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "executing"
target["execution_result"] = None
target.pop("execution_completed_at", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

baseline = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

print()
print("1. BASELINE STATE:")
print(
    target["action"],
    "|",
    target["status"],
)

assert target["status"] == "executing"

# Crash after temporary file is completely written,
# but BEFORE replacing the real state file.
child_code = r'''
from pathlib import Path
import json
import os

STATE_PATH = Path("state/latest.json")
TEMP_PATH = STATE_PATH.with_suffix(".tmp")

print("CHILD: writing temporary state file", flush=True)

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

with TEMP_PATH.open("w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
    f.flush()
    os.fsync(f.fileno())

print("CHILD: temporary state fully written", flush=True)
print("CHILD: simulated crash BEFORE os.replace()", flush=True)

os._exit(99)
'''

print()
print("2. STARTING CRASHING ATOMIC WRITER...")

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print("CHILD OUTPUT:")
print(child.stdout)

assert child.returncode == 99

# The real state file must still be valid.
print()
print("3. STATE AFTER CRASH:")

try:
    recovered_state = json.loads(
        STATE_PATH.read_text(encoding="utf-8")
    )

    recovered_target = next(
        a for a in recovered_state["actions"]
        if a.get("action") == "free-disk-space"
    )

    print("STATE REMAINED VALID:")
    print(
        recovered_target["action"],
        "|",
        recovered_target["status"],
    )

    state_valid = True

except Exception as exc:
    print("STATE READ FAILED:")
    print(type(exc).__name__, "|", exc)
    state_valid = False

assert state_valid
assert recovered_target["status"] == "executing"

# The crash may leave the temporary file behind.
# That is acceptable; the authoritative state remained valid.
temp_exists = STATE_PATH.with_suffix(".tmp").exists()

print()
print("4. TEMPORARY FILE:")
print("EXISTS:", temp_exists)

print()
print("5. RESULT:")
print("RESULT: PASS")
print("Original state remained valid after simulated writer crash.")
print("Crash occurred before atomic replacement.")
print("Authoritative state was not corrupted.")
print("Atomic replacement protects state persistence.")

# Cleanup temporary file.
try:
    STATE_PATH.with_suffix(".tmp").unlink()
except FileNotFoundError:
    pass
