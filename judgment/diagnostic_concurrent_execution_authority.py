import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json
from concurrent.futures import ThreadPoolExecutor

from judgment.execution import execute_action
from judgment.audit import load_audit
from judgment.lifecycle import retry_failed_action

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== CONCURRENT EXECUTION AUTHORITY RACE INVARIANT TEST ===")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "failed"
target["retry_count"] = 0
target["max_retries"] = 2
target["escalation_required"] = False
target["execution_result"] = "concurrent-execution-test"

open(STATE_PATH, "w", encoding="utf-8").write(json.dumps(state, indent=2))

print()
print("1. INITIAL FAILED STATE:")
print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

before = load_audit()

print()
print("2. EXPLICIT RETRY AUTHORIZATION:")
retry = retry_failed_action(ACTION)
print(retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1
print("PASS")

before_execution = load_audit()

print()
print("3. CONCURRENT EXECUTION ATTEMPTS:")

def attempt():
    return execute_action(ACTION)

with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(lambda _: attempt(), range(8)))

for i, result in enumerate(results, 1):
    print(f"THREAD {i}:", result)

successful = [r for r in results if r.get("status") == "executing"]
blocked = [r for r in results if r.get("status") == "blocked"]

print()
print("SUCCESSFUL EXECUTIONS:", len(successful))
print("BLOCKED EXECUTIONS:", len(blocked))

assert len(successful) == 1
assert len(blocked) == 7

print("PASS")

print()
print("4. DURABLE STATE:")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] == "executing"
assert target["retry_count"] == 1
assert target["escalation_required"] is False

print("PASS")

print()
print("5. AUDIT ATOMICITY:")

after = load_audit()

events = [
    e for e in after[len(before_execution):]
    if e.get("action") == ACTION
]

execution_started = [
    e for e in events
    if e.get("event") == "execution-started"
]

assert len(execution_started) == 1

print("TOTAL NEW EXECUTION EVENTS:", len(events))
print("EXECUTION-STARTED EVENTS:", len(execution_started))
print("PASS")

print()
print("6. FINAL CONCURRENCY INVARIANT:")
print("EXACTLY ONE THREAD ACQUIRED EXECUTION AUTHORITY")
print("ALL OTHER THREADS WERE BLOCKED")
print("EXECUTION AUTHORITY WAS NOT DOUBLE-GRANTED")
print("RETRY COUNT REMAINED 1")
print("NO ESCALATION WAS MANUFACTURED")
print("EXACTLY ONE EXECUTION-STARTED AUDIT EVENT EXISTS")
print("STATE REMAINED DURABLE")
print("AUDIT REMAINED CONSISTENT")
print()
print("RESULT: PASS")
