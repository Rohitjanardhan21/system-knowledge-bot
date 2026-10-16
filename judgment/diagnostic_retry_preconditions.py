import json
from pathlib import Path

from judgment.lifecycle import retry_failed_action

STATE_PATH = Path("state") / "latest.json"

print("=== RETRY PRECONDITION TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    action
    for action in state.get("actions", [])
    if action.get("action") == "free-disk-space"
)

target["status"] = "failed"
target["execution_result"] = "interrupted-by-restart"

print("FAILED ACTION:")
print(target.get("action"), "|", target.get("status"))

healthy_facts = {
    "memory": {"utilization": 60},
    "disk": {"utilization": 70},
}

result = retry_failed_action(
    target,
    current_facts=healthy_facts,
)

print()
print("RECOVERED SYSTEM RETRY:")
print(result)

assert result["status"] == "blocked"
assert target["status"] == "failed"

dangerous_facts = {
    "memory": {"utilization": 90},
    "disk": {"utilization": 93},
}

result = retry_failed_action(
    target,
    current_facts=dangerous_facts,
)

print()
print("STILL-DANGEROUS SYSTEM RETRY:")
print(result)

assert result["status"] == "approved"
assert target["status"] == "approved"

print()
print("RESULT: PASS")
print("Recovered conditions block stale retries.")
print("Current valid conditions allow explicit retry.")
