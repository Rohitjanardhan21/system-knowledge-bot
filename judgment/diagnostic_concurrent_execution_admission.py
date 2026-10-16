from __future__ import annotations

import json
import threading

from judgment.audit import load_audit
from judgment.execution import execute_action
from judgment.recovery import STATE_PATH

ACTION = "free-disk-space"

state = {
    "actions": [{
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
        "retry_count": 1,
        "max_retries": 1,
        "escalation_required": False,
        "execution_result": None,
    }]
}

STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

before = load_audit()

results = []
errors = []
lock = threading.Lock()


def worker(worker_id):
    try:
        result = execute_action(ACTION)

        with lock:
            results.append((worker_id, result))

    except Exception as exc:
        with lock:
            errors.append((worker_id, repr(exc)))


print()
print("=== CONCURRENT EXECUTION AUTHORIZATION RACE TEST ===")

print()
print("1. INITIAL DURABLE STATE:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| retry_count =", action["retry_count"],
    "| max_retries =", action["max_retries"],
)

assert action["status"] == "approved"
assert action["retry_count"] == 1
assert action["max_retries"] == 1

print("PASS")

print()
print("2. CONCURRENT EXECUTION REQUESTS:")

threads = [
    threading.Thread(target=worker, args=(i,))
    for i in range(1, 9)
]

for t in threads:
    t.start()

for t in threads:
    t.join()

for worker_id, result in sorted(results):
    print(f"worker-{worker_id}:", result)

for worker_id, error in sorted(errors):
    print(f"worker-{worker_id} ERROR:", error)

print("PASS")

print()
print("3. RESULT COUNTS:")

executing = [
    result for _, result in results
    if result.get("status") == "executing"
]

blocked = [
    result for _, result in results
    if result.get("status") == "blocked"
]

print("executing:", len(executing))
print("blocked:", len(blocked))
print("errors:", len(errors))

assert len(executing) == 1
assert len(blocked) == 7
assert len(errors) == 0

print("Exactly ONE execution was admitted.")
print("PASS")

print()
print("4. DURABLE STATE:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| retry_count =", action["retry_count"],
    "| max_retries =", action["max_retries"],
)

assert action["status"] == "executing"
assert action["retry_count"] == 1
assert action["max_retries"] == 1

print("Execution admission did not consume or modify retry budget.")
print("PASS")

print()
print("5. AUDIT:")

after = load_audit()

events = [
    e for e in after[len(before):]
    if e.get("action") == ACTION
]

for event in events:
    print(
        event.get("event"),
        "|",
        event.get("status"),
        "|",
        event.get("result"),
    )

started = [
    e for e in events
    if e.get("event") == "execution-started"
]

blocked_events = [
    e for e in events
    if e.get("event") in {
        "execution-blocked",
        "execution-not-available",
    }
]

assert len(started) == 1

print("Exactly one execution-started event was recorded.")
print("PASS")

print()
print("6. FINAL CONCURRENCY INVARIANTS:")

print("CONCURRENT EXECUTION REQUESTS DID NOT DOUBLE-ADMIT EXECUTION")
print("EXACTLY ONE WORKER ENTERED EXECUTION")
print("ALL OTHER WORKERS WERE BLOCKED")
print("RETRY BUDGET REMAINED IMMUTABLE")
print("NO SECOND EXECUTION WAS MANUFACTURED")
print("AUDIT PRESERVED EXECUTION ADMISSION")

print()
print("RESULT: PASS")
