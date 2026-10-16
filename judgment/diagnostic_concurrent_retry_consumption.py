import json
from concurrent.futures import ThreadPoolExecutor

from judgment.lifecycle import retry_failed_action
from judgment.audit import load_audit
from judgment.recovery import STATE_PATH


print("=== CONCURRENT RETRY AUTHORIZATION / RETRY-BUDGET RACE TEST ===")

ACTION = "free-disk-space"

state = {
    "actions": [{
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "failed",
        "retry_count": 0,
        "max_retries": 1,
        "escalation_required": False,
        "execution_result": "previous-failure",
    }]
}

STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

before = load_audit()

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

assert action["status"] == "failed"
assert action["retry_count"] == 0
assert action["max_retries"] == 1

print("PASS")

print()
print("2. CONCURRENT RETRY AUTHORIZATION:")

def authorize_retry(_):
    try:
        return retry_failed_action(ACTION)
    except Exception as exc:
        return {
            "status": "error",
            "error": repr(exc),
        }

with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(authorize_retry, range(8)))

for i, result in enumerate(results, 1):
    print(f"worker-{i}:", result)

print()
print("3. COUNT AUTHORIZATIONS:")

approved = [
    r for r in results
    if r.get("status") == "approved"
]

blocked = [
    r for r in results
    if r.get("status") == "blocked"
]

errors = [
    r for r in results
    if r.get("status") == "error"
]

print("approved:", len(approved))
print("blocked:", len(blocked))
print("errors:", len(errors))

assert len(approved) == 1
assert len(blocked) == 7
assert len(errors) == 0

print("Exactly ONE retry authorization was granted.")
print("PASS")

print()
print("4. DURABLE RETRY BUDGET:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| retry_count =", action["retry_count"],
    "| max_retries =", action["max_retries"],
    "| escalation =", action["escalation_required"],
)

assert action["retry_count"] == 1
assert action["max_retries"] == 1
assert action["escalation_required"] is False

print("Retry budget was consumed exactly once.")
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

approved_events = [
    e for e in events
    if e.get("event") == "retry-approved"
]

blocked_events = [
    e for e in events
    if e.get("event") == "retry-blocked"
]

assert len(approved_events) == 1
assert len(blocked_events) == 7

print("Audit contains exactly one authorization and seven blocks.")
print("PASS")

print()
print("6. FINAL CONCURRENCY INVARIANTS:")

print("CONCURRENT REQUESTS DID NOT DOUBLE-CONSUME RETRY BUDGET")
print("EXACTLY ONE RETRY WAS AUTHORIZED")
print("ALL OTHER REQUESTS WERE BLOCKED")
print("DURABLE retry_count = 1")
print("NO RETRY SLOT WAS MANUFACTURED")
print("AUDIT PRESERVED THE COMPETING REQUESTS")

print()
print("RESULT: PASS")
