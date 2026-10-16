
from pathlib import Path
import json
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.lifecycle import retry_failed_action, begin_execution, complete_execution
from judgment.executor import execute_plan
from judgment.audit import load_audit

STATE_PATH = Path("state/latest.json")

print("=== FAILURE → RETRY → RE-EXECUTION SAFETY TEST ===")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# 1. Establish deterministic failed state.
target["status"] = "failed"
target["execution_result"] = "simulated-previous-failure"
target.pop("execution_started_at", None)
target.pop("execution_completed_at", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print("1. FAILED STATE:")
print(target["action"], "|", target["status"])

# 2. Failed action cannot execute directly.
blocked = execute_plan([target], dry_run=True)

print()
print("2. DIRECT EXECUTION:")
print(blocked)

assert blocked[0]["result"] == "retry-required"

# 3. Explicit retry approval.
retry = retry_failed_action(target)

print()
print("3. RETRY APPROVAL:")
print(retry)

assert retry["status"] == "approved"
assert target["status"] == "approved"

# 4. Re-execution.
started = begin_execution(target)

print()
print("4. RE-EXECUTION START:")
print(started)

assert started["status"] == "executing"
assert target["status"] == "executing"

# 5. Complete successfully.
completed = complete_execution(
    target,
    success=True,
    result="retry-dry-run-success",
)

print()
print("5. RE-EXECUTION COMPLETE:")
print(completed)

assert completed["status"] == "executed"
assert target["status"] == "executed"

# 6. Duplicate execution remains blocked.
duplicate = execute_plan([target], dry_run=True)

print()
print("6. DUPLICATE EXECUTION:")
print(duplicate)

assert duplicate[0]["result"] == "already-executed"

# 7. Verify lifecycle audit sequence.
audit = load_audit()

events = [
    e.get("event")
    for e in audit
    if e.get("action") == "free-disk-space"
]

assert "retry-approved" in events
assert "execution-started" in events
assert "execution-completed" in events

print()
print("7. AUDIT:")
for event in audit[-8:]:
    print(
        event.get("event"),
        "|",
        event.get("status"),
        "|",
        event.get("result"),
    )

print()
print("RESULT: PASS")
print("Failed actions require explicit retry.")
print("Retry returns through approved → executing.")
print("Successful retry becomes executed.")
print("Duplicate execution remains blocked.")
print("Lifecycle transitions are durably audited.")
