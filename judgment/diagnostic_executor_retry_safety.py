from pathlib import Path
import json
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.executor import execute_plan
from judgment.lifecycle import retry_failed_action
from judgment.audit import load_audit
from state.state_reader import get_action_state

print("=== EXECUTOR RETRY SAFETY TEST ===")

STATE_PATH = Path("state/latest.json")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

action = get_action_state("free-disk-space")
assert action is not None, "free-disk-space action not found"

# Establish and persist a known failed state.
action["status"] = "failed"
action["execution_result"] = "simulated-execution-failure"

for stored in state.get("actions", []):
    if stored.get("action") == "free-disk-space":
        stored.clear()
        stored.update(action)
        break

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print("INITIAL:")
print(action["action"], "|", action["status"])

# Direct executor attempt must not bypass the retry lifecycle.
before = load_audit()

direct = execute_plan(
    [action],
    dry_run=True,
)

print()
print("DIRECT EXECUTOR ATTEMPT:")
print(direct)

persisted = get_action_state("free-disk-space")

print()
print("STATE AFTER DIRECT ATTEMPT:")
print(
    persisted.get("action"),
    "|",
    persisted.get("status"),
    "|",
    persisted.get("execution_result"),
)

assert persisted.get("status") == "failed", (
    "Executor bypassed retry lifecycle and changed failed action state."
)

# Explicit retry approval is required.
retry = retry_failed_action(persisted)

print()
print("EXPLICIT RETRY:")
print(retry)

assert retry["status"] == "approved"

# Execute only after explicit retry approval.
retry_plan = [{
    **persisted,
    "status": "approved",
    "execution_mode": "automatic",
}]

executor_result = execute_plan(
    retry_plan,
    dry_run=True,
)

print()
print("EXECUTOR AFTER RETRY APPROVAL:")
print(executor_result)

final_state = get_action_state("free-disk-space")

print()
print("FINAL PERSISTED STATE:")
print(
    final_state.get("action"),
    "|",
    final_state.get("status"),
    "|",
    final_state.get("execution_result"),
)

assert final_state.get("status") == "executed", (
    "Explicitly retried action did not reach executed state."
)

# A successfully executed action must remain terminal.
second_result = execute_plan(
    [{
        **final_state,
        "execution_mode": "automatic",
    }],
    dry_run=True,
)

print()
print("SECOND EXECUTOR ATTEMPT:")
print(second_result)

second_state = get_action_state("free-disk-space")

assert second_state.get("status") == "executed", (
    "Duplicate execution changed an already executed action."
)

print()
print("RESULT: PASS")
print("Failed actions cannot bypass retry approval.")
print("Executor uses the lifecycle boundary.")
print("Explicit retry may transition failed -> approved -> executing -> executed.")
print("Successfully executed actions remain terminal.")
print("Duplicate execution is prevented.")
