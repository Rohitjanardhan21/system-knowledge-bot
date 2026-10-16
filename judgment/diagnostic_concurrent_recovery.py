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

print("=== CONCURRENT RECOVERY RACE INVARIANT TEST ===")

# ------------------------------------------------------------
# 1. INITIAL INTERRUPTED STATE
# ------------------------------------------------------------

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "approved"
target["retry_count"] = 1
target["max_retries"] = 2
target["escalation_required"] = False
target["execution_result"] = None

open(STATE_PATH, "w", encoding="utf-8").write(
    json.dumps(state, indent=2)
)

start = execute_action(ACTION)

assert start["status"] == "executing"

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

assert target["status"] == "executing"
assert target["retry_count"] == 1
assert target["escalation_required"] is False

print()
print("1. INITIAL INTERRUPTED STATE:")
print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

before = load_audit()

# ------------------------------------------------------------
# 2. CONCURRENT RECOVERY ATTEMPTS
# ------------------------------------------------------------

print()
print("2. CONCURRENT RECOVERY ATTEMPTS:")

results = []

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [
        executor.submit(recover_interrupted_actions)
        for _ in range(8)
    ]

    for index, future in enumerate(as_completed(futures), start=1):
        result = future.result()
        results.append(result)
        print(f"THREAD {index}: {result}")

recovered_count = sum(
    ACTION in result
    for result in results
)

print()
print("RECOVERY CLAIMS:", recovered_count)

# Exactly one recovery operation must claim the action.
assert recovered_count == 1

print("PASS")

# ------------------------------------------------------------
# 3. DURABLE STATE
# ------------------------------------------------------------

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

# ------------------------------------------------------------
# 4. AUDIT ATOMICITY
# ------------------------------------------------------------

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

print("TOTAL NEW ACTION EVENTS:", len(events))
print("RECOVERY-INTERRUPTED EVENTS:", len(recovery_events))

assert len(recovery_events) == 1

event = recovery_events[0]

assert event.get("status") == "failed"
assert event.get("result") == "interrupted-by-restart"

print("PASS")

# ------------------------------------------------------------
# 5. FINAL CONCURRENCY INVARIANT
# ------------------------------------------------------------

print()
print("5. FINAL CONCURRENCY INVARIANT:")

print("EXACTLY ONE RECOVERY CLAIM WON")
print("ALL OTHER RECOVERY ATTEMPTS OBSERVED THE RECOVERED STATE")
print("EXECUTING → FAILED TRANSITION OCCURRED EXACTLY ONCE")
print("INTERRUPTED RESULT WAS WRITTEN EXACTLY ONCE")
print("RETRY COUNT WAS NOT MODIFIED")
print("ESCALATION STATE WAS NOT MODIFIED")
print("EXACTLY ONE RECOVERY AUDIT EVENT EXISTS")
print("NO RETRY AUTHORITY WAS MANUFACTURED")
print("STATE AND AUDIT REMAINED CONSISTENT")

print("RESULT: PASS")
