import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from judgment.execution import execute_action
from judgment.recovery import recover_interrupted_actions
from judgment.audit import load_audit

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== CONCURRENT RECOVERY → EXECUTION AUTHORITY RACE INVARIANT TEST ===")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "executing"
target["retry_count"] = 1
target["max_retries"] = 2
target["escalation_required"] = False
target["execution_result"] = None

open(STATE_PATH, "w", encoding="utf-8").write(
    json.dumps(state, indent=2)
)

before = load_audit()

print()
print("1. INITIAL INTERRUPTED STATE:")
print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

def recovery_worker():
    return recover_interrupted_actions()

def execution_worker():
    return execute_action(ACTION)

print()
print("2. CONCURRENT RECOVERY + EXECUTION:")

results = []

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = []

    for _ in range(4):
        futures.append(("recovery", executor.submit(recovery_worker)))

    for _ in range(4):
        futures.append(("execution", executor.submit(execution_worker)))

    for kind, future in futures:
        try:
            results.append((kind, future.result()))
        except Exception as exc:
            results.append((kind, {"error": repr(exc)}))

for i, (kind, result) in enumerate(results, 1):
    print(f"THREAD {i} [{kind}]:", result)

recovery_claims = [
    r for kind, r in results
    if kind == "recovery" and ACTION in r
]

execution_claims = [
    r for kind, r in results
    if kind == "execution" and r.get("status") == "executing"
]

print()
print("RECOVERY CLAIMS:", len(recovery_claims))
print("EXECUTION CLAIMS:", len(execution_claims))

assert len(recovery_claims) == 1
assert len(execution_claims) == 0

print("PASS")

print()
print("3. DURABLE STATE:")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "|", target["status"],
    "|", target.get("execution_result"),
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"
assert target["retry_count"] == 1
assert target["escalation_required"] is False

print("PASS")

print()
print("4. AUDIT ATOMICITY:")

after = load_audit()

events = [
    e for e in after[len(before):]
    if e.get("action") == ACTION
]

recovery_events = [
    e for e in events
    if e.get("event") == "recovery-interrupted"
]

execution_events = [
    e for e in events
    if e.get("event") == "execution-started"
]

print("TOTAL NEW ACTION EVENTS:", len(events))
print("RECOVERY-INTERRUPTED EVENTS:", len(recovery_events))
print("EXECUTION-STARTED EVENTS:", len(execution_events))

assert len(recovery_events) == 1
assert len(execution_events) == 0

print("PASS")

print()
print("5. FINAL CONCURRENCY INVARIANT:")
print("EXACTLY ONE RECOVERY CLAIM WON")
print("NO EXECUTION CLAIM ACQUIRED AUTHORITY AGAINST INTERRUPTED STATE")
print("RECOVERY CONVERTED EXECUTING → FAILED EXACTLY ONCE")
print("EXECUTION AUTHORITY WAS NOT DOUBLE-GRANTED")
print("RETRY COUNT REMAINED UNCHANGED")
print("ESCALATION STATE REMAINED UNCHANGED")
print("EXACTLY ONE RECOVERY AUDIT EVENT EXISTS")
print("NO EXECUTION-STARTED AUDIT EVENT EXISTS")
print("STATE AND AUDIT REMAINED CONSISTENT")
print("RESULT: PASS")
