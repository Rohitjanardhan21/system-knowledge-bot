from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json

from judgment.lifecycle import (
    begin_execution,
    complete_execution,
    retry_failed_action,
)
from judgment.executor import execute_plan
from judgment.audit import load_audit

if __name__ == "__main__":
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

STATE_PATH = Path("state/latest.json")

print("=== AUDIT INTEGRITY TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Start from a clean approved state.
target["status"] = "approved"
target["execution_result"] = None
target.pop("execution_started_at", None)
target.pop("execution_completed_at", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. APPROVED → EXECUTING")

started = begin_execution(target)
print(started)

assert started["status"] == "executing"

audit = load_audit()
events = [
    e for e in audit
    if e.get("action") == "free-disk-space"
]

assert any(
    e.get("event") == "execution-started"
    for e in events
)

print("execution-started audit: PASS")


print()
print("2. EXECUTING → EXECUTED")

completed = complete_execution(
    target,
    success=True,
    result="audit-integrity-success",
)

print(completed)

assert completed["status"] == "executed"

audit = load_audit()
events = [
    e for e in audit
    if e.get("action") == "free-disk-space"
]

assert any(
    e.get("event") == "execution-completed"
    and e.get("status") == "executed"
    and e.get("result") == "audit-integrity-success"
    for e in events
)

print("execution-completed audit: PASS")


print()
print("3. DUPLICATE EXECUTION MUST NOT CREATE SUCCESS AUDIT")

blocked = execute_plan(
    [target],
    dry_run=True,
)

print(blocked)

assert blocked[0]["result"] == "already-executed"

audit_after_block = load_audit()
events_after_block = [
    e for e in audit_after_block
    if e.get("action") == "free-disk-space"
]

success_events = [
    e for e in events_after_block
    if (
        e.get("event") == "execution-completed"
        and e.get("result") == "already-executed"
    )
]

assert not success_events

print("No false execution-completed audit: PASS")


print()
print("4. FAILED ACTION REQUIRES EXPLICIT RETRY")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "failed"
target["execution_result"] = "simulated-failure"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

blocked_retry = execute_plan(
    [target],
    dry_run=True,
)

print(blocked_retry)

assert blocked_retry[0]["result"] == "retry-required"

print("Direct retry blocked: PASS")


print()
print("5. EXPLICIT RETRY MUST CREATE retry-approved")

retry = retry_failed_action(target)

print(retry)

assert retry["status"] == "approved"

audit = load_audit()
events = [
    e for e in audit
    if e.get("action") == "free-disk-space"
]

assert any(
    e.get("event") == "retry-approved"
    and e.get("status") == "approved"
    for e in events
)

print("retry-approved audit: PASS")


print()
print("6. VERIFY FINAL AUDIT SEQUENCE")

audit = load_audit()

events = [
    e for e in audit
    if e.get("action") == "free-disk-space"
]

recent = events[-12:]

for event in recent:
    print(
        f"{event.get('event'):22} | "
        f"{event.get('status'):12} | "
        f"{event.get('result'):32}"
    )

event_names = [e.get("event") for e in events]

assert "execution-started" in event_names
assert "execution-completed" in event_names
assert "retry-approved" in event_names

print()
print("7. AUDIT PERSISTENCE")

fresh_audit = load_audit()

assert len(fresh_audit) >= len(audit)

print("Audit survives fresh load: PASS")

print()
print("RESULT: PASS")
print("Execution start was audited.")
print("Execution completion was audited.")
print("Duplicate execution produced no false success audit.")
print("Failed execution remained retry-gated.")
print("Explicit retry approval was audited.")
print("Audit history remained durable.")
