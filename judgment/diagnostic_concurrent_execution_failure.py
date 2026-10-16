import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json
from concurrent.futures import ThreadPoolExecutor

from judgment.execution import execute_action
from judgment.lifecycle import retry_failed_action
from judgment.audit import load_audit

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== CONCURRENT EXECUTION FAILURE RACE INVARIANT TEST ===")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "failed"
target["retry_count"] = 0
target["max_retries"] = 2
target["escalation_required"] = False
target["execution_result"] = "failure-race-test"

open(STATE_PATH, "w", encoding="utf-8").write(
    json.dumps(state, indent=2)
)

print()
print("1. INITIAL FAILED STATE:")
print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

print()
print("2. EXPLICIT RETRY AUTHORIZATION:")
retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
print("PASS")

print()
print("3. START EXECUTION:")
start = execute_action(ACTION)
print("START:", start)

assert start["status"] == "executing"
print("PASS")

before = load_audit()

print()
print("4. CONCURRENT FAILURE REPORTING:")

def report_failure(label):
    return execute_action(
        ACTION,
        result=label,
        complete=True,
    )

failure_results = [
    "worker-1-failure",
    "worker-2-failure",
    "worker-3-failure",
    "worker-4-failure",
    "worker-5-failure",
    "worker-6-failure",
    "worker-7-failure",
    "worker-8-failure",
]

with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(
        executor.map(report_failure, failure_results)
    )

for i, result in enumerate(results, 1):
    print(f"THREAD {i}:", result)

successful = [
    r for r in results
    if r.get("status") == "executed"
]

blocked = [
    r for r in results
    if r.get("status") == "blocked"
]

print()
print("SUCCESSFUL COMPLETIONS:", len(successful))
print("BLOCKED COMPLETIONS:", len(blocked))

assert len(successful) == 1
assert len(blocked) == 7

print("PASS")

print()
print("5. DURABLE FINAL STATE:")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "|", target["status"],
    "| result =", target.get("execution_result"),
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] == "executed"
assert target["retry_count"] == 1
assert target["escalation_required"] is False
assert target["execution_result"] in failure_results

print("PASS")

print()
print("6. AUDIT ATOMICITY:")

after = load_audit()

events = [
    e for e in after[len(before):]
    if e.get("action") == ACTION
]

completion_events = [
    e for e in events
    if e.get("event") == "execution-completed"
]

assert len(completion_events) == 1

audit_result = completion_events[0].get("result")

assert audit_result == target["execution_result"]

print("TOTAL NEW EVENTS:", len(events))
print("EXECUTION-COMPLETED EVENTS:", len(completion_events))
print("AUDIT RESULT:", audit_result)
print("PASS")

print()
print("7. FINAL FAILURE-RACE INVARIANT:")
print("EXACTLY ONE FAILURE REPORT WON")
print("ALL OTHER REPORTS WERE REJECTED")
print("FINAL RESULT WAS WRITTEN EXACTLY ONCE")
print("NO COMPETING FAILURE OVERWROTE THE WINNING RESULT")
print("RETRY COUNT REMAINED 1")
print("ESCALATION REMAINED CLEARED")
print("EXACTLY ONE EXECUTION-COMPLETED AUDIT EVENT EXISTS")
print("STATE AND AUDIT REMAINED CONSISTENT")
print()
print("RESULT: PASS")
