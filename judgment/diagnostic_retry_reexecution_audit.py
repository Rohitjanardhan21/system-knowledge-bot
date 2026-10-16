from judgment.lifecycle import retry_failed_action, begin_execution, complete_execution
from judgment.audit import load_audit
from state.state_reader import get_action_state

print("=== RETRY RE-EXECUTION AUDIT TEST ===")

action = get_action_state("free-disk-space")
assert action is not None, "free-disk-space action not found"

# Establish a known failed state.
action["status"] = "failed"
action["execution_result"] = "simulated-execution-failure"

before = load_audit()

retry = retry_failed_action(action)
print("RETRY:")
print(retry)

assert retry["status"] == "approved"

start = begin_execution(action)
print("RE-EXECUTION START:")
print(start)

assert start["status"] == "executing"

complete = complete_execution(
    action,
    success=True,
    result="retry-dry-run-success",
)
print("RE-EXECUTION COMPLETE:")
print(complete)

assert complete["status"] == "executed"

after = load_audit()
new_entries = after[len(before):]

print()
print("NEW AUDIT EVENTS:")

for entry in new_entries:
    print(
        f"{entry.get('event'):22} | "
        f"{entry.get('status'):12} | "
        f"{entry.get('result'):28} | "
        f"{entry.get('action')}"
    )

events = [
    entry.get("event")
    for entry in new_entries
    if entry.get("action") == "free-disk-space"
]

assert "retry-approved" in events, "retry-approved audit event missing"
assert "execution-started" in events, "execution-started audit event missing"
assert "execution-completed" in events, "execution-completed audit event missing"

retry_index = events.index("retry-approved")
start_index = events.index("execution-started")
complete_index = events.index("execution-completed")

assert retry_index < start_index < complete_index, (
    "Retry audit events are out of lifecycle order."
)

print()
print("RESULT: PASS")
print("Retry approval is durably audited.")
print("Retry execution start is durably audited.")
print("Retry execution completion is durably audited.")
print("Lifecycle audit ordering is preserved.")
