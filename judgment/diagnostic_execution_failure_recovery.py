from pathlib import Path
import json
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.lifecycle import begin_execution, complete_execution
from judgment.lifecycle import retry_failed_action
from judgment.audit import load_audit

STATE_PATH = Path("state/latest.json")

print("=== EXECUTION FAILURE → RETRY SAFETY TEST ===")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Known starting point.
target["status"] = "approved"
target["execution_result"] = None
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
assert target["status"] == "executing"

print("PASS")

print()
print("2. EXECUTION FAILURE")

failed = complete_execution(
    target,
    success=False,
    result="simulated-handler-failure",
)

print(failed)

assert failed["status"] == "failed"
assert target["status"] == "failed"
assert target["execution_result"] == "simulated-handler-failure"

print("PASS")

print()
print("3. PERSISTED FAILURE")

persisted = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

persisted_target = next(
    a for a in persisted["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    persisted_target["action"],
    "|",
    persisted_target["status"],
    "|",
    persisted_target.get("execution_result"),
)

assert persisted_target["status"] == "failed"
assert persisted_target["execution_result"] == "simulated-handler-failure"

print("PASS")

print()
print("4. FAILED → EXECUTING WITHOUT RETRY MUST BE BLOCKED")

blocked = begin_execution(target)
print(blocked)

assert blocked["status"] == "blocked"

print("PASS")

print()
print("5. EXPLICIT RETRY APPROVAL")

retry = retry_failed_action(target)
print(retry)

assert retry["status"] == "approved"
assert target["status"] == "approved"

print("PASS")

print()
print("6. RETRY → EXECUTING")

retry_start = begin_execution(target)
print(retry_start)

assert retry_start["status"] == "executing"

print("PASS")

print()
print("7. RETRY EXECUTION SUCCEEDS")

completed = complete_execution(
    target,
    success=True,
    result="retry-after-failure-success",
)

print(completed)

assert completed["status"] == "executed"
assert target["status"] == "executed"
assert target["execution_result"] == "retry-after-failure-success"

print("PASS")

print()
print("8. FINAL PERSISTED STATE")

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
    final_target.get("execution_result"),
)

assert final_target["status"] == "executed"
assert final_target["execution_result"] == "retry-after-failure-success"

print("PASS")

print()
print("9. AUDIT")

audit = load_audit()

events = [
    e for e in audit
    if e.get("action") == "free-disk-space"
]

for event in events[-10:]:
    print(
        f"{event.get('event'):22} | "
        f"{event.get('status'):12} | "
        f"{event.get('result')}"
    )

assert any(
    e.get("event") == "execution-started"
    for e in events
)

assert any(
    e.get("event") == "retry-approved"
    for e in events
)

print()
print("RESULT: PASS")
print("Execution failure became failed.")
print("Failed execution was persisted.")
print("Direct re-execution was blocked.")
print("Explicit retry approval succeeded.")
print("Retry execution completed successfully.")
print("Final executed state was persisted.")
print("Failure → retry → execution lifecycle is safe.")
