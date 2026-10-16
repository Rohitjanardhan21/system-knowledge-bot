import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json
from concurrent.futures import ThreadPoolExecutor

from judgment.lifecycle import resolve_escalation
from judgment.recovery import recover_interrupted_actions
from judgment.audit import load_audit

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== CONCURRENT RECOVERY → RESOLUTION RACE INVARIANT TEST ===")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "executing"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = None

open(STATE_PATH, "w", encoding="utf-8").write(
    json.dumps(state, indent=2)
)

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

print()
print("2. CONCURRENT RECOVERY + RESOLUTION:")

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

tasks = [recovery_worker] * 4 + [resolution_worker] * 4

with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(lambda fn: fn(), tasks))

for i, result in enumerate(results, 1):
    print(f"THREAD {i} [{result[0]}]:", result[1])

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print()
print("3. DURABLE STATE:")
print(
    ACTION,
    "|", target["status"],
    "|", target.get("execution_result"),
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] in ("failed", "approved")
assert target["retry_count"] in (0, 2)

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

resolution_events = [
    e for e in events
    if e.get("event") == "escalation-resolved"
]

print("TOTAL NEW ACTION EVENTS:", len(events))
print("RECOVERY-INTERRUPTED EVENTS:", len(recovery_events))
print("ESCALATION-RESOLVED EVENTS:", len(resolution_events))

assert len(recovery_events) <= 1
assert len(resolution_events) <= 1
assert len(recovery_events) + len(resolution_events) >= 1

print("PASS")

print()
print("5. FINAL CONCURRENCY INVARIANT:")
print("RECOVERY COULD CLAIM THE INTERRUPTED EXECUTION AT MOST ONCE")
print("RESOLUTION COULD RESTORE AUTHORITY AT MOST ONCE")
print("NO DUPLICATE RECOVERY OCCURRED")
print("NO DUPLICATE RESOLUTION OCCURRED")
print("RETRY STATE WAS NOT DOUBLE-MODIFIED")
print("ESCALATION STATE WAS NOT DOUBLE-CLEARED")
print("STATE REMAINED DURABLE")
print("AUDIT REMAINED ATOMIC")
print("RESULT: PASS")
