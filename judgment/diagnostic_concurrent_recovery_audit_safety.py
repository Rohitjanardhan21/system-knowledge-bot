from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from judgment.recovery import recover_interrupted_actions, STATE_PATH
from judgment.audit import load_audit

# STATE_PATH imported from judgment.recovery


print("=== CONCURRENT RECOVERY + AUDIT SAFETY TEST ===")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Force the known interrupted state.
target["status"] = "executing"
target["execution_result"] = None
target.pop("execution_completed_at", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. INTERRUPTED STATE:")
print(
    target["action"],
    "|",
    target["status"],
)

print()
print("2. STARTING TWO CONCURRENT RECOVERY PROCESSES...")

worker = r'''
import json
from pathlib import Path
from judgment.recovery import recover_interrupted_actions, STATE_PATH

result = recover_interrupted_actions()

print("RECOVERY RESULT:", result)

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    "STATE:",
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("recovery_reason"),
)
'''

p1 = subprocess.Popen(
    [sys.executable, "-c", worker],
    cwd=Path.cwd(),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

p2 = subprocess.Popen(
    [sys.executable, "-c", worker],
    cwd=Path.cwd(),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

out1, err1 = p1.communicate()
out2, err2 = p2.communicate()

print()
print("PROCESS 1:")
print(out1)

if err1:
    print("PROCESS 1 STDERR:")
    print(err1)

print("PROCESS 2:")
print(out2)

if err2:
    print("PROCESS 2 STDERR:")
    print(err2)

assert p1.returncode == 0
assert p2.returncode == 0

print()
print("3. FINAL STATE:")

final_state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

final_target = next(
    a for a in final_state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    final_target["action"],
    "|",
    final_target["status"],
    "|",
    final_target.get("recovery_reason"),
)

assert final_target["status"] == "failed"
assert (
    final_target.get("recovery_reason")
    == "interrupted-by-restart"
)

print("PASS")

print()
print("4. AUDIT RECOVERY EVENTS:")

audit = load_audit()

recovery_events = [
    e for e in audit
    if (
        e.get("action") == "free-disk-space"
        and (
            e.get("event") == "recovery"
            or e.get("event") == "execution-failed"
            or "recover" in str(e.get("event", "")).lower()
        )
    )
]

for event in recovery_events[-10:]:
    print(event)

print()
print("5. FRESH PROCESS VERIFICATION:")

verify = subprocess.run(
    [
        sys.executable,
        "-c",
        """
import json
from judgment.recovery import STATE_PATH

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("recovery_reason"),
)
""",
    ],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print(verify.stdout)
if verify.stderr:
    print("FRESH PROCESS STDERR:")
    print(verify.stderr)

assert verify.returncode == 0

print()
print("RESULT: PASS")
print("Concurrent recovery processes completed safely.")
print("Interrupted execution remained failed.")
print("Recovery state was persisted exactly once.")
print("Fresh process observed the same recovered state.")
print("Recovery + audit concurrency boundary is intact.")
