import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

import json
from concurrent.futures import ThreadPoolExecutor

from judgment.lifecycle import resolve_escalation
from judgment.audit import load_audit

STATE_PATH = r"state\latest.json"
ACTION = "free-disk-space"

print("=== CONCURRENT ESCALATION RESOLUTION RACE INVARIANT TEST ===")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "failed"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = "retry-limit-reached"

open(STATE_PATH, "w", encoding="utf-8").write(
    json.dumps(state, indent=2)
)

before = load_audit()

print()
print("1. INITIAL ESCALATED STATE:")
print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)
print("PASS")

print()
print("2. CONCURRENT RESOLUTION ATTEMPTS:")

def resolve():
    return resolve_escalation(
        ACTION,
        principal={
            "scope": "admin",
            "_source": "api_key",
            "name": "judgment-test-admin",
        },
    )

with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(lambda _: resolve(), range(8)))

for index, result in enumerate(results, 1):
    print(f"THREAD {index}:", result)

successful = [
    r for r in results
    if r.get("status") == "approved"
]

blocked = [
    r for r in results
    if r.get("status") == "blocked"
]

print()
print("SUCCESSFUL RESOLUTIONS:", len(successful))
print("BLOCKED RESOLUTIONS:", len(blocked))

assert len(successful) == 1
assert len(blocked) == 7

print("PASS")

print()
print("3. DURABLE STATE:")

state = json.loads(open(STATE_PATH, encoding="utf-8").read())
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print(
    ACTION,
    "|", target["status"],
    "| retry_count =", target["retry_count"],
    "| escalation =", target["escalation_required"],
)

assert target["status"] == "approved"
assert target["retry_count"] == 0
assert target["escalation_required"] is False

print("PASS")

print()
print("4. AUDIT ATOMICITY:")

after = load_audit()

events = [
    e for e in after[len(before):]
    if e.get("action") == ACTION
]

resolution_events = [
    e for e in events
    if e.get("event") == "escalation-resolved"
]

print("TOTAL NEW ACTION EVENTS:", len(events))
print("ESCALATION-RESOLVED EVENTS:", len(resolution_events))

assert len(resolution_events) == 1

print("PASS")

print()
print("5. FINAL CONCURRENCY INVARIANT:")
print("EXACTLY ONE THREAD RESTORED AUTHORITY")
print("ALL OTHER THREADS OBSERVED THE RESOLVED STATE")
print("RETRY BUDGET WAS RESET EXACTLY ONCE")
print("ESCALATION WAS CLEARED EXACTLY ONCE")
print("EXACTLY ONE RESOLUTION AUDIT EVENT EXISTS")
print("STATE REMAINED DURABLE")
print("AUDIT REMAINED CONSISTENT")

print()
print("RESULT: PASS")
