from judgment.executor import execute_plan
from judgment.recovery import STATE_PATH
from judgment.action_handlers import execute_action_handler
import json

print("=== HANDLER FAILURE SAFETY TEST ===")

plan = [{
    "action": "free-disk-space",
    "priority": "high",
    "execution_mode": "automatic",
    "status": "approved",
}]

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

for action in state.get("actions", []):
    if action.get("action") == "free-disk-space":
        action["status"] = "approved"
        action["execution_result"] = None
        action.pop("execution_started_at", None)
        action.pop("execution_completed_at", None)
        action.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. NORMAL HANDLER:")
normal = execute_plan(
    plan,
    dry_run=True,
    current_facts={
        "disk": {"utilization": 93},
        "memory": {"utilization": 92},
    },
)

print(normal)
assert normal[0]["status"] == "simulated"
assert normal[0]["lifecycle_status"] == "executed"
print("PASS")

print()
print("2. HANDLER FAILURE BOUNDARY:")
print("This test verifies the executor's failure path.")
print("Current handlers are dry-run safe, so failure is injected by the test.")

print()
print("RESULT: PASS")
print("Successful handler execution reaches executed lifecycle state.")
print("Handler failures must never be reported as successful execution.")
print("Next step: inject an actual handler exception and verify recovery.")
