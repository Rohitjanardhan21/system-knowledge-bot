import json
import threading
import time
from pathlib import Path

from judgment.lifecycle import (
    STATE_PATH,
    begin_execution,
    complete_execution,
    retry_failed_action,
    run_execution_side_effect,
    state_lock,
)


ACTION = "free-disk-space"
SANDBOX = Path("state") / "authorization_toctou_reauthorization_sandbox"
SANDBOX.mkdir(parents=True, exist_ok=True)

file_a = SANDBOX / "cleanup_a.tmp"
file_b = SANDBOX / "cleanup_b.tmp"

for f in (file_a, file_b):
    f.write_text("temporary data", encoding="utf-8")


def load_state():
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state):
    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def set_status(status, result=None):
    with state_lock():
        state = load_state()
        action = state["actions"][0]
        action["status"] = status

        if result is not None:
            action["execution_result"] = result

        save_state(state)


# Fresh deterministic state.
save_state({
    "actions": [{
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "approved",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_result": None,
        "execution_generation": None,
    }]
})


print()
print("=== AUTHORIZATION TOCTOU → REVOCATION → RE-AUTHORIZATION TEST ===")

print()
print("1. INITIAL REAL-WORLD STATE:")
print("A:", file_a.exists())
print("B:", file_b.exists())

assert file_a.exists()
assert file_b.exists()
print("PASS")


print()
print("2. WORKER A EXECUTION:")

start_a = begin_execution(ACTION)
print("WORKER A:", start_a)

assert start_a["status"] == "executing"
generation_a = start_a["execution_generation"]

print("Generation A:", generation_a)
print("PASS")


print()
print("3. SIDE-EFFECT / REVOCATION RACE SETUP:")

side_effect_entered = threading.Event()
revocation_requested = threading.Event()


def worker_a_side_effect():
    print("Worker A side effect entered.")
    side_effect_entered.set()

    # Give the revocation thread a chance to request the lock.
    revocation_requested.wait(timeout=5)

    # IMPORTANT:
    # run_execution_side_effect itself holds state_lock while
    # executing this callback.
    #
    # Therefore authorization revocation cannot interleave
    # inside this critical section.
    time.sleep(0.25)

    if file_a.exists():
        file_a.unlink()
        return "deleted-a"

    return "already-absent"


revocation_result = {}


def revoke_authorization():
    side_effect_entered.wait(timeout=5)

    print("Revocation thread requesting lifecycle lock...")
    revocation_requested.set()

    # This must wait until Worker A's side-effect admission
    # and side effect have completed.
    set_status(
        "rejected",
        "authorization-revoked-after-side-effect-admission",
    )

    revocation_result["done"] = True
    print("Authorization revocation committed.")


revocation_thread = threading.Thread(
    target=revoke_authorization,
    name="authorization-revoker",
)

revocation_thread.start()

print("PASS")


print()
print("4. WORKER A SIDE-EFFECT ADMISSION:")

side_effect_result = run_execution_side_effect(
    ACTION,
    generation_a,
    worker_a_side_effect,
)

print("SIDE EFFECT:", side_effect_result)

revocation_thread.join(timeout=5)

assert side_effect_result["status"] == "allowed"
assert side_effect_result["value"] == "deleted-a"

print("Worker A's side effect was admitted.")
print("PASS")


print()
print("5. VERIFY REVOCATION WON AFTER SIDE-EFFECT LINEARIZATION:")

state = load_state()
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| generation =", action.get("execution_generation"),
)

assert action["status"] == "rejected"
assert action["execution_result"] == (
    "authorization-revoked-after-side-effect-admission"
)

print("Authorization revocation is durable.")
print("PASS")


print()
print("6. VERIFY REAL-WORLD SIDE EFFECT SURVIVED:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert file_b.exists()

print("Real-world mutation occurred before revocation.")
print("PASS")


print()
print("7. WORKER A ATTEMPTS COMPLETION AFTER REVOCATION:")

completion_a = complete_execution(
    ACTION,
    success=True,
    result="WORKER-A-UNAUTHORIZED-SUCCESS",
    execution_generation=generation_a,
)

print("WORKER A COMPLETION:", completion_a)

state = load_state()
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
)

assert action["status"] == "rejected"
assert action["execution_result"] != "WORKER-A-UNAUTHORIZED-SUCCESS"

print("Worker A could not manufacture success.")
print("PASS")


print()
print("8. RETRY BYPASS ATTEMPT:")

retry_a = retry_failed_action(ACTION)

print("RETRY:", retry_a)

state = load_state()
action = state["actions"][0]

assert retry_a["status"] == "blocked"
assert action["status"] == "rejected"
assert action["retry_count"] == 0

print("Rejected action cannot bypass revocation through retry.")
print("PASS")


print()
print("9. EXPLICIT RE-AUTHORIZATION:")

# Simulate a new authorization decision.
set_status(
    "approved",
    "explicitly-reauthorized-after-revocation",
)

state = load_state()
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| retry_count =", action["retry_count"],
)

assert action["status"] == "approved"

print("PASS")


print()
print("10. WORKER B STARTS NEW GENERATION:")

start_b = begin_execution(ACTION)

print("WORKER B:", start_b)

assert start_b["status"] == "executing"

generation_b = start_b["execution_generation"]

print(
    "Generation A:", generation_a,
    "| Generation B:", generation_b,
)

assert generation_b > generation_a

print("New authorization received a new execution generation.")
print("PASS")


print()
print("11. STALE WORKER A ATTEMPTS SIDE EFFECT:")

def stale_side_effect():
    print("ERROR: stale side effect callback executed!")
    return "STALE-MUTATION"


stale = run_execution_side_effect(
    ACTION,
    generation_a,
    stale_side_effect,
)

print("STALE WORKER A:", stale)

assert stale["status"] == "blocked"
assert stale["result"] == "stale-execution-generation"

print("Stale Worker A remained fenced.")
print("PASS")


print()
print("12. VERIFY STALE WORKER DID NOT MUTATE WORLD:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert file_b.exists()

print("PASS")


print()
print("13. WORKER B SIDE-EFFECT RECONCILIATION:")

def worker_b_side_effect():
    # A is already absent because Worker A changed the world
    # before its authorization was revoked.
    if file_a.exists():
        file_a.unlink()
        return "deleted-a"

    return "already-absent"


side_effect_b = run_execution_side_effect(
    ACTION,
    generation_b,
    worker_b_side_effect,
)

print("WORKER B SIDE EFFECT:", side_effect_b)

assert side_effect_b["status"] == "allowed"
assert side_effect_b["value"] == "already-absent"

print("Worker B reconciled the existing world state.")
print("PASS")


print()
print("14. WORKER B COMPLETES:")

completion_b = complete_execution(
    ACTION,
    success=True,
    result="REAUTHORIZED-RECONCILIATED-SUCCESS",
    execution_generation=generation_b,
)

print("WORKER B COMPLETION:", completion_b)

assert completion_b["status"] == "executed"

print("PASS")


print()
print("15. FINAL DURABLE STATE:")

state = load_state()
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
    "| generation =", action.get("execution_generation"),
)

assert action["status"] == "executed"
assert action["execution_result"] == (
    "REAUTHORIZED-RECONCILIATED-SUCCESS"
)
assert action["execution_generation"] == generation_b
assert action["retry_count"] == 0

print("PASS")


print()
print("16. FINAL REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert not file_a.exists()
assert file_b.exists()

print("PASS")


print()
print("17. HARD AUTHORIZATION-TOCTOU INVARIANTS:")

print("SIDE-EFFECT ADMISSION WAS ATOMIC WITH AUTHORIZATION REVOCATION")
print("REVOCATION COULD NOT INTERLEAVE INSIDE THE SIDE-EFFECT CRITICAL SECTION")
print("SIDE EFFECT WAS NOT RETROACTIVELY CLAIMED AS UNAUTHORIZED")
print("REVOKED WORKER COULD NOT MANUFACTURE COMPLETION")
print("REJECTED ACTION COULD NOT BYPASS REVOCATION THROUGH RETRY")
print("RE-AUTHORIZATION CREATED A NEW EXECUTION GENERATION")
print("STALE GENERATION COULD NOT MUTATE THE WORLD")
print("NEW WORKER RECONCILED THE EXISTING REAL-WORLD STATE")
print("FINAL DURABLE STATE MATCHED THE REAUTHORIZED GENERATION")
print("AUDITABLE LIFECYCLE REMAINED CONSISTENT")


print()
print("Cleaning sandbox...")

for f in (file_a, file_b):
    if f.exists():
        f.unlink()

try:
    SANDBOX.rmdir()
except OSError:
    pass

print()
print("RESULT: PASS")
