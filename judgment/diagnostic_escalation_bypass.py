import json

from judgment.recovery import STATE_PATH
from judgment.executor import execute_plan
from judgment.lifecycle import MAX_RETRIES

print("=== ESCALATION BYPASS SAFETY TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "failed"
target["retry_count"] = MAX_RETRIES
target["max_retries"] = MAX_RETRIES
target["escalation_required"] = True
target["execution_result"] = "retry-limit-reached"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. ESCALATED STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "| retry_count =",
    target.get("retry_count"),
    "| max_retries =",
    target.get("max_retries"),
    "| escalation =",
    target.get("escalation_required"),
)

assert target["status"] == "failed"
assert target["retry_count"] >= target["max_retries"]
assert target["escalation_required"] is True

print("PASS")

print()
print("2. DIRECT EXECUTOR BYPASS ATTEMPT:")

plan = [{
    "action": "free-disk-space",
    "priority": "high",
    "execution_mode": "automatic",
    "status": "approved",
}]

results = execute_plan(
    plan,
    dry_run=True,
    current_facts={
        "disk": {"utilization": 93},
        "memory": {"utilization": 92},
    },
)

print(results)

assert results[0]["status"] == "blocked"
assert results[0]["result"] in {
    "retry-limit-reached",
    "retry-required",
    "already-executed",
    "lifecycle-blocked",
}

print("PASS")

print()
print("3. STATE AFTER BYPASS ATTEMPT:")

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
    "| retry_count =",
    target.get("retry_count"),
    "| escalation =",
    target.get("escalation_required"),
)

assert target["status"] == "failed"
assert target["retry_count"] >= target["max_retries"]
assert target["escalation_required"] is True

print("PASS")

print()
print("RESULT: PASS")
print("Escalated actions cannot bypass the retry limit.")
print("Direct execution does not clear escalation.")
print("Retry exhaustion remains authoritative.")
