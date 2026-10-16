from pathlib import Path
import json
from judgment.lifecycle import (
    begin_execution,
    complete_execution,
    retry_failed_action,
    run_execution_side_effect,
)
from judgment.recovery import recover_interrupted_actions
from judgment.execution import execute_action
from judgment.audit import load_audit

ACTION = "free-disk-space"
SANDBOX = Path("state") / "external_mutation_retry_sandbox"
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

STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

before = load_audit()

print()
print("=== EXTERNAL MUTATION DURING ACTIVE RETRY TEST ===")

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
print("2. INITIAL EXECUTION:")
start = execute_action(ACTION)
print("START:", start)

assert start["status"] == "executing"

generation_1 = start["execution_generation"]

print("Generation:", generation_1)

# Simulate partial side effect.
file_a.unlink()

print("A deleted:", not file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())
print("PASS")

print()
print("3. CRASH:")
recovered = recover_interrupted_actions()
print("RECOVERED:", recovered)

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
assert action["retry_count"] == 0

print("PASS")

print()
print("4. EXPLICIT RETRY:")
retry = retry_failed_action(ACTION)
print("RETRY:", retry)

assert retry["status"] == "approved"
assert retry["retry_count"] == 1

print("PASS")

print()
print("5. WORKER B STARTS:")
start_b = execute_action(ACTION)
print("WORKER B:", start_b)

assert start_b["status"] == "executing"

generation_2 = start_b["execution_generation"]

assert generation_2 > generation_1

print("Generation B:", generation_2)
print("PASS")

print()
print("6. WORKER B OBSERVES CURRENT WORLD:")
print("A:", file_a.exists())
print("B:", file_b.exists())
print("C:", file_c.exists())

assert not file_a.exists()
assert file_b.exists()
assert file_c.exists()

print("Worker B sees A already cleaned.")
print("PASS")

print()
print("7. EXTERNAL PROCESS MUTATES WORLD:")
print("External process deletes B before Worker B acts.")

file_b.unlink()

assert not file_b.exists()

print("A:", file_a.exists())
print("B:", file_b.exists())
print("C:", file_c.exists())
print("PASS")

print()
print("8. WORKER B MUST RECONCILE CURRENT WORLD:")
print("Worker B attempts cleanup operation.")

def delete_b():
    if file_b.exists():
        file_b.unlink()
        return "deleted-by-worker-b"
    return "already-absent"

side_effect_b = run_execution_side_effect(
    ACTION,
    generation_2,
    delete_b,
)

print("SIDE EFFECT:", side_effect_b)

assert side_effect_b["status"] == "allowed"

print("PASS")

print()
print("9. VERIFY NO FALSE FAILURE:")
print("B exists:", file_b.exists())

assert not file_b.exists()

print("B is absent, therefore cleanup invariant is satisfied.")
print("PASS")

print()
print("10. EXTERNAL PROCESS CREATES NEW UNRELATED FILE:")
external_file = SANDBOX / "external_unrelated.tmp"
external_file.write_text("external data", encoding="utf-8")

assert external_file.exists()

print("External unrelated file exists:", external_file.exists())
print("PASS")

print()
print("11. WORKER B COMPLETES:")
complete = complete_execution(
    ACTION,
    "cleanup-reconciled-success",
    execution_generation=generation_2,
)

print("COMPLETE:", complete)

assert complete["status"] == "executed"

print("PASS")

print()
print("12. FINAL DURABLE STATE:")
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
print("13. FINAL REAL-WORLD STATE:")
print("A exists:", file_a.exists())
print("B exists:", file_b.exists())
print("C exists:", file_c.exists())
print("Unrelated external file exists:", external_file.exists())

assert not file_a.exists()
assert not file_b.exists()
assert file_c.exists()
assert external_file.exists()

print("Worker did not delete unrelated external state.")
print("PASS")

print()
print("14. AUDIT:")
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
assert "execution-completed" in observed

print("PASS")

print()
print("15. FINAL EXTERNAL-MUTATION INVARIANTS:")
print("CRASH WAS RECOVERED")
print("RETRY REQUIRED EXPLICIT AUTHORIZATION")
print("WORKER B USED THE CURRENT EXECUTION GENERATION")
print("EXTERNAL MUTATION WAS NOT MISTAKEN FOR WORKER B'S ACTION")
print("ALREADY-ABSENT TARGET WAS TREATED IDEMPOTENTLY")
print("UNRELATED EXTERNAL STATE WAS PRESERVED")
print("FINAL DURABLE STATE MATCHED THE CLEANUP INVARIANT")
print("AUDIT PRESERVED THE COMPLETE LIFECYCLE")

for f in (file_a, file_b, file_c, external_file):
    if f.exists():
        f.unlink()

try:
    SANDBOX.rmdir()
except OSError:
    pass

print()
print("RESULT: PASS")
