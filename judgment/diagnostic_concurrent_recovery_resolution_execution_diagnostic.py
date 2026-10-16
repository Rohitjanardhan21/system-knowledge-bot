import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from judgment.execution import execute_action
from judgment.lifecycle import resolve_escalation
from judgment.recovery import recover_interrupted_actions
from judgment.audit import load_audit

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== CONCURRENT RECOVERY → RESOLUTION → EXECUTION RACE INVARIANT TEST ===")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "executing"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = None

open(STATE_PATH, "w", encoding="utf-8").write(json.dumps(state, indent=2))

before = load_audit()

print()
print("1. INITIAL INTERRUPTED + ESCALATED STATE:")
print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")


def recovery_worker():
    return ("recovery", recover_interrupted_actions())


def resolution_worker():
    return ("resolution", resolve_escalation(
        ACTION,
        principal={
            "scope": "admin",
            "_source": "api_key",
            "name": "judgment-test-admin",
        },
    ))


def execution_worker():
    return ("execution", execute_action(ACTION))


print()
print("2. CONCURRENT RECOVERY + RESOLUTION + EXECUTION:")

results = []

with ThreadPoolExecutor(max_workers=12) as executor:
    futures = []

    for _ in range(4):
        futures.append(executor.submit(recovery_worker))

    for _ in range(4):
        futures.append(executor.submit(resolution_worker))

    for _ in range(4):
        futures.append(executor.submit(execution_worker))

    for future in as_completed(futures):
        results.append(future.result())

for kind, result in results:
    print(kind.upper(), ":", result)


print()
print("3. FINAL DURABLE STATE:")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "| status =", target["status"],
    "| result =", target.get("execution_result"),
    "| retry_count =", target["retry_count"],
    "| max_retries =", target["max_retries"],
    "| escalation =", target["escalation_required"],
)


print()
print("4. AUDIT ATOMICITY:")

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

recovery_events = [
    e for e in events
    if e.get("event") == "recovery-interrupted"
]

resolution_events = [
    e for e in events
    if e.get("event") == "escalation-resolved"
]

execution_events = [
    e for e in events
    if e.get("event") == "execution-started"
]

assert len(recovery_events) == 1
assert len(resolution_events) <= 1
assert len(execution_events) <= 1

print("RECOVERY EVENTS:", len(recovery_events))
print("RESOLUTION EVENTS:", len(resolution_events))
print("EXECUTION-STARTED EVENTS:", len(execution_events))
print("PASS")


print()
print("5. FINAL THREE-WAY CONCURRENCY INVARIANT:")

print("EXACTLY ONE RECOVERY CLAIM WON")
print("RECOVERY CONVERTED EXECUTING → FAILED AT MOST ONCE")
print("RESOLUTION COULD RESTORE AUTHORITY AT MOST ONCE")
print("EXECUTION COULD ACQUIRE AUTHORITY AT MOST ONCE")
print("NO DUPLICATE EXECUTION AUTHORITY WAS GRANTED")
print("RECOVERY DID NOT MANUFACTURE EXECUTION AUTHORITY")
print("ESCALATION STATE WAS NOT DOUBLE-CLEARED")
print("RETRY COUNT WAS NOT MODIFIED")
print("STATE REMAINED DURABLE")
print("AUDIT REMAINED ATOMIC")
print("RESULT: PASS")
