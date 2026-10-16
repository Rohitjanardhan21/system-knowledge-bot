import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from judgment.execution import execute_action
from judgment.lifecycle import retry_failed_action
from judgment.recovery import recover_interrupted_actions
from judgment.audit import load_audit

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== CONCURRENT RECOVERY → RETRY RACE INVARIANT TEST ===")

# ------------------------------------------------------------
# 1. CREATE INTERRUPTED EXECUTION
# ------------------------------------------------------------

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "approved"
target["retry_count"] = 0
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

print()
print("1. INITIAL EXECUTING STATE:")
print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

before = load_audit()

# ------------------------------------------------------------
# 2. CONCURRENT RECOVERY
# ------------------------------------------------------------

print()
print("2. CONCURRENT RECOVERY:")

recovery_results = []

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [
        executor.submit(recover_interrupted_actions)
        for _ in range(8)
    ]

    for index, future in enumerate(as_completed(futures), start=1):
        result = future.result()
        recovery_results.append(result)
        print(f"THREAD {index}: {result}")

successful_recoveries = sum(
    ACTION in result
    for result in recovery_results
)

assert successful_recoveries == 1

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"
assert target["retry_count"] == 0
assert target["escalation_required"] is False

print("SUCCESSFUL RECOVERIES:", successful_recoveries)
print("PASS")

# ------------------------------------------------------------
# 3. CONCURRENT RETRY AUTHORIZATION
# ------------------------------------------------------------

print()
print("3. CONCURRENT RETRY ATTEMPTS:")

retry_results = []

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [
        executor.submit(retry_failed_action, ACTION)
        for _ in range(8)
    ]

    for index, future in enumerate(as_completed(futures), start=1):
        result = future.result()
        retry_results.append(result)
        print(f"THREAD {index}: {result}")

successful_retries = [
    result
    for result in retry_results
    if result.get("status") == "approved"
]

blocked_retries = [
    result
    for result in retry_results
    if result.get("status") == "blocked"
]

assert len(successful_retries) == 1
assert len(blocked_retries) == 7

winning_retry = successful_retries[0]

assert winning_retry["retry_count"] == 1
assert winning_retry["escalation_required"] is False

print()
print("SUCCESSFUL RETRIES:", len(successful_retries))
print("BLOCKED RETRIES:", len(blocked_retries))
print("PASS")

# ------------------------------------------------------------
# 4. DURABLE STATE
# ------------------------------------------------------------

print()
print("4. DURABLE STATE:")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| max_retries =", target["max_retries"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] == "approved"
assert target["retry_count"] == 1
assert target["max_retries"] == 2
assert target["escalation_required"] is False

print("PASS")

# ------------------------------------------------------------
# 5. AUDIT ATOMICITY
# ------------------------------------------------------------

print()
print("5. AUDIT ATOMICITY:")

after = load_audit()

events = [
    e for e in after[len(before):]
    if e.get("action") == ACTION
]

recovery_events = [
    e for e in events
    if e.get("event") == "recovery-interrupted"
]

retry_events = [
    e for e in events
    if e.get("event") == "retry-approved"
]

print("TOTAL NEW ACTION EVENTS:", len(events))
print("RECOVERY-INTERRUPTED EVENTS:", len(recovery_events))
print("RETRY-APPROVED EVENTS:", len(retry_events))

assert len(recovery_events) == 1
assert len(retry_events) == 1

print("PASS")

# ------------------------------------------------------------
# 6. FINAL CROSS-RACE INVARIANT
# ------------------------------------------------------------

print()
print("6. FINAL CROSS-RACE INVARIANT:")

print("EXACTLY ONE RECOVERY CLAIM WON")
print("RECOVERY CONVERTED EXECUTING → FAILED EXACTLY ONCE")
print("RECOVERY PRESERVED RETRY COUNT")
print("EXACTLY ONE RETRY AUTHORIZATION WON")
print("ALL COMPETING RETRIES WERE BLOCKED")
print("RETRY COUNT INCREASED EXACTLY ONCE")
print("NO DOUBLE-CONSUMPTION OCCURRED")
print("NO ESCALATION WAS MANUFACTURED")
print("EXACTLY ONE RECOVERY AUDIT EVENT EXISTS")
print("EXACTLY ONE RETRY-APPROVED AUDIT EVENT EXISTS")
print("STATE AND AUDIT REMAINED CONSISTENT")

print("RESULT: PASS")
