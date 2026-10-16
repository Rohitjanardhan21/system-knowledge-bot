from pathlib import Path
import json
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.recovery import recover_interrupted_actions
from judgment.lifecycle import retry_failed_action, begin_execution, complete_execution
from judgment.executor import execute_plan
from judgment.audit import load_audit

STATE_PATH = Path("state/latest.json")

print("=== CRASH → RECOVERY → RETRY → RE-EXECUTION TEST ===")

# 1. Establish interrupted execution state
state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "executing"
target["execution_result"] = None
target.pop("execution_completed_at", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. INTERRUPTED STATE:")
print(target["action"], "|", target["status"])

# 2. Recover after restart
recovered = recover_interrupted_actions()

print()
print("2. RECOVERY:")
print("RECOVERED:", recovered)

assert "free-disk-space" in recovered

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)

assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"

# 3. Direct execution must be blocked
blocked = execute_plan([target], dry_run=True)

print()
print("3. DIRECT EXECUTION AFTER RECOVERY:")
print(blocked)

assert blocked[0]["result"] == "retry-required"

# 4. Explicit retry approval
retry = retry_failed_action(target)

print()
print("4. EXPLICIT RETRY:")
print(retry)

assert retry["status"] == "approved"
assert target["status"] == "approved"

# 5. Re-execution
started = begin_execution(target)

print()
print("5. RE-EXECUTION START:")
print(started)

assert started["status"] == "executing"

# 6. Complete successfully
completed = complete_execution(
    target,
    success=True,
    result="recovery-retry-success",
)

print()
print("6. RE-EXECUTION COMPLETE:")
print(completed)

assert completed["status"] == "executed"

# 7. Verify persistence
persisted = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

persisted_target = next(
    a for a in persisted["actions"]
    if a.get("action") == "free-disk-space"
)

print()
print("7. PERSISTED FINAL STATE:")
print(
    persisted_target["action"],
    "|",
    persisted_target["status"],
    "|",
    persisted_target.get("execution_result"),
)

assert persisted_target["status"] == "executed"
assert persisted_target["execution_result"] == "recovery-retry-success"

# 8. Verify audit trail
audit = load_audit()

events = [
    e for e in audit
    if e.get("action") == "free-disk-space"
]

print()
print("8. RECENT AUDIT:")
for event in events[-8:]:
    print(
        f"{event.get('event'):22} | "
        f"{event.get('status'):12} | "
        f"{event.get('result'):28}"
    )

event_names = [e.get("event") for e in events]

assert "retry-approved" in event_names
assert "execution-started" in event_names
assert "execution-completed" in event_names

print()
print("RESULT: PASS")
print("Interrupted execution was recovered as failed.")
print("Direct retry was blocked.")
print("Explicit retry approval succeeded.")
print("Re-execution completed successfully.")
print("Final executed state was persisted.")
print("Lifecycle audit remained durable.")
