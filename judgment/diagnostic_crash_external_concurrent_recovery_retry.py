from pathlib import Path
import json
import threading
from judgment.execution import execute_action
from judgment.recovery import recover_interrupted_actions
from judgment.lifecycle import retry_failed_action, run_execution_side_effect, complete_execution
from judgment.audit import load_audit

ACTION = "free-disk-space"
SANDBOX = Path("state") / "crash_external_race_sandbox"
SANDBOX.mkdir(parents=True, exist_ok=True)

file_a = SANDBOX / "cleanup_a.tmp"
file_b = SANDBOX / "cleanup_b.tmp"
file_c = SANDBOX / "cleanup_c.tmp"

for f in (file_a, file_b, file_c):
    f.write_text("temporary data", encoding="utf-8")

STATE_PATH = Path("state") / "latest.json"

state = {
    "actions": [{
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_result": None,
    }]
}

STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

before = load_audit()

print()
print("=== CRASH + EXTERNAL MUTATION + CONCURRENT RECOVERY/RETRY RACE TEST ===")

print()
print("1. INITIAL REAL-WORLD STATE:")
print("A:", file_a.exists())
print("B:", file_b.exists())
print("C:", file_c.exists())

assert file_a.exists()
assert file_b.exists()
assert file_c.exists()
print("PASS")

print()
print("2. WORKER A EXECUTION:")
start_a = execute_action(ACTION)

print("WORKER A:", start_a)

assert start_a["status"] == "executing"

generation_a = start_a["execution_generation"]

print("Generation A:", generation_a)
print("PASS")

print()
print("3. WORKER A PRODUCES REAL-WORLD SIDE EFFECT:")

file_a.unlink()

assert not file_a.exists()
assert file_b.exists()
assert file_c.exists()

print("A deleted:", not file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())
print("PASS")

print()
print("4. WORKER A CRASHES BEFORE COMPLETION:")
print("Durable completion is intentionally absent.")
print("PASS")

print()
print("5. CONCURRENT RECOVERY RACE:")

recovery_results = []
recovery_errors = []

def recovery_worker(name):
    try:
        result = recover_interrupted_actions()
        recovery_results.append((name, result))
    except Exception as exc:
        recovery_errors.append((name, repr(exc)))

threads = [
    threading.Thread(
        target=recovery_worker,
        args=(f"recovery-{i}",)
    )
    for i in range(1, 5)
]

for t in threads:
    t.start()

for t in threads:
    t.join()

for item in recovery_results:
    print(item)

for item in recovery_errors:
    print("ERROR:", item)

assert not recovery_errors

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
)

assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
assert action["retry_count"] == 0

print("Exactly one durable recovery state exists.")
print("PASS")

print()
print("6. EXTERNAL PROCESS MUTATES WORLD AFTER RECOVERY:")

print("External process deletes B.")
file_b.unlink()

assert not file_b.exists()
assert file_c.exists()

print("A:", file_a.exists())
print("B:", file_b.exists())
print("C:", file_c.exists())
print("PASS")

print()
print("7. CONCURRENT RETRY AUTHORIZATION RACE:")

retry_results = []
retry_errors = []

def retry_worker(name):
    try:
        result = retry_failed_action(ACTION)
        retry_results.append((name, result))
    except Exception as exc:
        retry_errors.append((name, repr(exc)))

threads = [
    threading.Thread(
        target=retry_worker,
        args=(f"retry-{i}",)
    )
    for i in range(1, 5)
]

for t in threads:
    t.start()

for t in threads:
    t.join()

for item in retry_results:
    print(item)

for item in retry_errors:
    print("ERROR:", item)

assert not retry_errors

approved = [
    r for _, r in retry_results
    if r.get("status") == "approved"
]

blocked = [
    r for _, r in retry_results
    if r.get("status") == "blocked"
]

assert len(approved) == 1
assert len(blocked) == 3

print("Approved:", len(approved))
print("Blocked:", len(blocked))
print("Exactly ONE retry authorization granted.")
print("PASS")

print()
print("8. VERIFY DURABLE RETRY BUDGET:")

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
assert action["max_retries"] == 2

print("PASS")

print()
print("9. WORKER B EXECUTION:")

start_b = execute_action(ACTION)

print("WORKER B:", start_b)

assert start_b["status"] == "executing"

generation_b = start_b["execution_generation"]

assert generation_b > generation_a

print("Generation A:", generation_a)
print("Generation B:", generation_b)
print("PASS")

print()
print("10. STALE WORKER A ATTEMPTS SIDE EFFECT:")

stale_attempt = run_execution_side_effect(
    ACTION,
    generation_a,
    lambda: file_c.unlink()
)

print("STALE ATTEMPT:", stale_attempt)

assert stale_attempt["status"] == "blocked"
assert stale_attempt["result"] == "stale-execution-generation"

assert file_c.exists()

print("STALE WORKER WAS FENCED.")
print("C remains:", file_c.exists())
print("PASS")

print()
print("11. WORKER B RECONCILES CURRENT WORLD:")

print("A:", file_a.exists())
print("B:", file_b.exists())
print("C:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()

def delete_c_if_needed():
    if file_c.exists():
        file_c.unlink()
        return "deleted-c"
    return "already-absent"

side_effect_b = run_execution_side_effect(
    ACTION,
    generation_b,
    delete_c_if_needed,
)

print("WORKER B SIDE EFFECT:", side_effect_b)

assert side_effect_b["status"] == "allowed"
assert not file_c.exists()

print("PASS")

print()
print("12. WORKER B COMPLETES:")

completion = complete_execution(
    ACTION,
    "cleanup-reconciled-success",
    execution_generation=generation_b,
)

print("COMPLETION:", completion)

assert completion["status"] == "executed"

print("PASS")

print()
print("13. FINAL DURABLE STATE:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
    "| generation =", action.get("execution_generation"),
)

assert action["status"] == "executed"
assert action["retry_count"] == 1

print("PASS")

print()
print("14. FINAL REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())

assert not file_a.exists()
assert not file_b.exists()
assert not file_c.exists()

print("All cleanup targets absent.")
print("PASS")

print()
print("15. AUDIT LIFECYCLE:")

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

observed = [e.get("event") for e in events]

assert "execution-started" in observed
assert "recovery-interrupted" in observed
assert "retry-approved" in observed
assert "retry-blocked" in observed
assert "execution-completed" in observed

execution_starts = [
    e for e in events
    if e.get("event") == "execution-started"
]

retry_approvals = [
    e for e in events
    if e.get("event") == "retry-approved"
]

assert len(execution_starts) == 2
assert len(retry_approvals) == 1

print("PASS")

print()
print("16. FINAL HARD INVARIANTS:")
print("ONE RECOVERY STATE WAS DURABLY ESTABLISHED")
print("EXTERNAL MUTATION DID NOT CORRUPT DURABLE STATE")
print("EXACTLY ONE RETRY WAS AUTHORIZED")
print("CONCURRENT RETRY REQUESTS DID NOT DOUBLE-CONSUME BUDGET")
print("WORKER B RECEIVED A NEW EXECUTION GENERATION")
print("STALE WORKER A COULD NOT MUTATE THE WORLD")
print("WORKER B OPERATED AGAINST CURRENT WORLD STATE")
print("FINAL DURABLE STATE MATCHED REAL-WORLD STATE")
print("AUDIT PRESERVED RECOVERY + RETRY RACE + FENCING + COMPLETION")

for f in (file_a, file_b, file_c):
    if f.exists():
        f.unlink()

try:
    SANDBOX.rmdir()
except OSError:
    pass

print()
print("RESULT: PASS")
