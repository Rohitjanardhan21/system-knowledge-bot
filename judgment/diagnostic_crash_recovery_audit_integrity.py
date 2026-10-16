from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.audit import AUDIT_PATH, load_audit
from judgment.lifecycle import retry_failed_action
from judgment.recovery import recover_interrupted_actions

STATE_PATH = Path("state/latest.json")


print("=== CRASH → RECOVERY → RETRY → AUDIT INTEGRITY TEST ===")


# ---------------------------------------------------------
# 1. Prepare an executing action
# ---------------------------------------------------------

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

print()
print("1. INTERRUPTED EXECUTING STATE")
print(
    target["action"],
    "|",
    target["status"],
)

assert target["status"] == "executing"


# ---------------------------------------------------------
# 2. Simulate restart recovery
# ---------------------------------------------------------

print()
print("2. RESTART RECOVERY")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

assert "free-disk-space" in recovered

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

assert target["status"] == "failed"
assert target.get("execution_result") == "interrupted-by-restart"

print("PASS")


# ---------------------------------------------------------
# 3. Recovery must be idempotent
# ---------------------------------------------------------

print()
print("3. SECOND RECOVERY MUST DO NOTHING")

second_recovery = recover_interrupted_actions()

print("RECOVERED:", second_recovery)

assert second_recovery == []

print("PASS")


# ---------------------------------------------------------
# 4. Direct execution must remain blocked
# ---------------------------------------------------------

print()
print("4. FAILED → EXECUTION WITHOUT RETRY MUST BE BLOCKED")

from judgment.lifecycle import begin_execution

blocked = begin_execution(target)

print(blocked)

assert blocked["status"] == "blocked"

print("PASS")


# ---------------------------------------------------------
# 5. Explicit retry approval
# ---------------------------------------------------------

print()
print("5. EXPLICIT RETRY APPROVAL")

retry = retry_failed_action(target)

print(retry)

assert retry["status"] == "approved"
assert target["status"] == "approved"

print("PASS")


# ---------------------------------------------------------
# 6. Retry execution
# ---------------------------------------------------------

print()
print("6. RETRY → EXECUTING")

started = begin_execution(target)

print(started)

assert started["status"] == "executing"

print("PASS")


# ---------------------------------------------------------
# 7. Complete retry
# ---------------------------------------------------------

print()
print("7. RETRY → EXECUTED")

from judgment.lifecycle import complete_execution

completed = complete_execution(
    target,
    success=True,
    result="crash-recovery-retry-audit-success",
)

print(completed)

assert completed["status"] == "executed"
assert target["status"] == "executed"

print("PASS")


# ---------------------------------------------------------
# 8. Verify durable final state
# ---------------------------------------------------------

print()
print("8. FINAL PERSISTED STATE")

fresh_state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

fresh_target = next(
    a for a in fresh_state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    fresh_target["action"],
    "|",
    fresh_target["status"],
    "|",
    fresh_target.get("execution_result"),
)

assert fresh_target["status"] == "executed"
assert (
    fresh_target["execution_result"]
    == "crash-recovery-retry-audit-success"
)

print("PASS")


# ---------------------------------------------------------
# 9. Verify audit lifecycle
# ---------------------------------------------------------

print()
print("9. AUDIT INTEGRITY")

audit = load_audit()

events = [
    e for e in audit
    if e.get("action") == "free-disk-space"
]

for event in events[-12:]:
    print(
        f"{event.get('event'):22} | "
        f"{event.get('status'):12} | "
        f"{event.get('result')}"
    )

event_names = [
    e.get("event")
    for e in events
]

assert "execution-started" in event_names
assert "retry-approved" in event_names
assert "execution-completed" in event_names

assert any(
    e.get("event") == "execution-failed"
    and e.get("status") == "failed"
    for e in events
)

assert any(
    e.get("event") == "retry-approved"
    and e.get("status") == "approved"
    for e in events
)

assert any(
    e.get("event") == "execution-completed"
    and e.get("result")
    == "crash-recovery-retry-audit-success"
    for e in events
)

print("PASS")


# ---------------------------------------------------------
# 10. Fresh-process verification
# ---------------------------------------------------------

print()
print("10. FRESH PROCESS VERIFICATION")

child_code = r'''
import json
from pathlib import Path

from judgment.audit import load_audit

STATE_PATH = Path("state/latest.json")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print("CHILD STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)

audit = load_audit()

events = [
    e for e in audit
    if e.get("action") == "free-disk-space"
]

print("CHILD AUDIT EVENTS:", len(events))

assert target["status"] == "executed"

assert any(
    e.get("event") == "execution-completed"
    and e.get("result")
    == "crash-recovery-retry-audit-success"
    for e in events
)
'''

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print(child.stdout)

if child.stderr:
    print("CHILD STDERR:")
    print(child.stderr)

assert child.returncode == 0

print("PASS")


# ---------------------------------------------------------
# 11. Duplicate execution protection
# ---------------------------------------------------------

print()
print("11. DUPLICATE EXECUTION MUST REMAIN BLOCKED")

duplicate_code = r'''
import json
from pathlib import Path

from judgment.lifecycle import begin_execution

STATE_PATH = Path("state/latest.json")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

result = begin_execution(target)

print(result)

assert result["status"] == "blocked"
'''

duplicate = subprocess.run(
    [sys.executable, "-c", duplicate_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print(duplicate.stdout)

if duplicate.stderr:
    print("CHILD STDERR:")
    print(duplicate.stderr)

assert duplicate.returncode == 0

print("PASS")


print()
print("RESULT: PASS")
print("Interrupted execution was recovered as failed.")
print("Recovery was idempotent.")
print("Direct execution remained retry-gated.")
print("Explicit retry approval was audited.")
print("Retry execution completed successfully.")
print("Final executed state was persisted.")
print("Fresh process observed the same final state.")
print("Duplicate execution remained blocked.")
print("Crash → recovery → retry → execution → audit integrity is intact.")
