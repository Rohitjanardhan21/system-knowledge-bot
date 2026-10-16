import json

from state.state_reader import get_action_state
from judgment.lifecycle import MAX_RETRIES, retry_failed_action
from judgment.executor import execute_plan
from judgment.audit import load_audit
from judgment.recovery import STATE_PATH

print("=== FULL EXECUTION SAFETY CHAIN ===")

state_data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
target = next(
    item for item in state_data["actions"]
    if item.get("action") == "free-disk-space"
)
target["status"] = "failed"
target["retry_count"] = 0
target["max_retries"] = MAX_RETRIES
target["escalation_required"] = False
target["execution_result"] = "simulated-previous-failure"
target.pop("execution_started_at", None)
target.pop("execution_completed_at", None)
target.pop("recovery_reason", None)
STATE_PATH.write_text(
    json.dumps(state_data, indent=2),
    encoding="utf-8",
)

action = get_action_state("free-disk-space")
assert action is not None

print("1. INITIAL STATE:")
print(action["action"], "|", action.get("status"))

print()
print("2. EXPLICIT RETRY:")
retry = retry_failed_action(action)
print(retry)
assert retry["status"] == "approved"

print()
print("3. EXECUTION:")
results = execute_plan([action], dry_run=True)
print(results)

state = get_action_state("free-disk-space")

print()
print("4. PERSISTED FINAL STATE:")
print(
    state["action"],
    "|",
    state["status"],
    "|",
    state.get("execution_result"),
)

assert state["status"] == "executed"

print()
print("5. DUPLICATE EXECUTION:")
duplicate = execute_plan([state], dry_run=True)
print(duplicate)

assert duplicate[0]["status"] == "blocked"
assert duplicate[0]["result"] == "already-executed"

print()
print("6. AUDIT:")
audit = load_audit()
recent = audit[-10:]

for entry in recent:
    event = str(entry.get("event", "legacy"))
    status = str(entry.get("status", "unknown"))
    result = str(entry.get("result", "unknown"))
    action_name = str(entry.get("action", "unknown"))

    print(
        f"{event:22} | "
        f"{status:12} | "
        f"{result:28} | "
        f"{action_name}"
    )

events = [e.get("event") for e in audit]

assert "retry-approved" in events
assert "execution-started" in events
assert "execution-completed" in events

print()
print("RESULT: PASS")
print("Full retry → execution → persistence → duplicate-protection chain is intact.")
print("Lifecycle and executor boundaries are integrated.")
print("Durable audit records the execution lifecycle.")
