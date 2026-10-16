import json
from pathlib import Path

from judgment.lifecycle import (
    STATE_PATH,
    begin_execution,
    can_execute,
    complete_execution,
    retry_failed_action,
    run_execution_side_effect,
    record_execution,
)


ACTION = "free-disk-space"
SANDBOX = Path("state") / "authorization_revocation_sandbox"
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


# Fresh deterministic lifecycle state.
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
        "execution_generation": None,
    }]
}

save_state(state)

print()
print("=== AUTHORIZATION REVOCATION DURING ACTIVE EXECUTION TEST ===")

print()
print("1. INITIAL REAL-WORLD STATE:")
print("A:", file_a.exists())
print("B:", file_b.exists())

assert file_a.exists()
assert file_b.exists()
print("PASS")

print()
print("2. INITIAL AUTHORIZATION:")
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
print("3. WORKER A EXECUTION ADMISSION:")

start = begin_execution(ACTION)
print("WORKER A:", start)

assert start["status"] == "executing"
generation_a = start["execution_generation"]

print("Worker A generation:", generation_a)
print("PASS")

print()
print("4. VERIFY ACTIVE EXECUTION:")

state = load_state()
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| generation =", action.get("execution_generation"),
)

assert action["status"] == "executing"
assert action["execution_generation"] == generation_a
print("PASS")

print()
print("5. AUTHORIZATION REVOCATION DURING EXECUTION:")

state = load_state()
action = state["actions"][0]

# Simulate an external authority revoking permission while
# Worker A is already executing.
action["status"] = "rejected"
action["execution_result"] = "authorization-revoked-during-execution"

save_state(state)

state = load_state()
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action["execution_result"],
)

assert action["status"] == "rejected"
print("Authorization revoked.")
print("PASS")

print()
print("6. WORKER A ATTEMPTS REAL-WORLD SIDE EFFECT:")

def delete_a():
    if file_a.exists():
        file_a.unlink()
        return "deleted-a"
    return "already-absent"


side_effect = run_execution_side_effect(
    ACTION,
    generation_a,
    delete_a,
)

print("SIDE EFFECT:", side_effect)

print("A exists after authorization revocation:", file_a.exists())

# Critical invariant:
# revoked execution MUST NOT be allowed to mutate the world.
assert file_a.exists()

print("PASS: revoked Worker A could not mutate the filesystem.")

print()
print("7. WORKER A ATTEMPTS COMPLETION:")

completion = complete_execution(
    ACTION,
    success=True,
    result="UNAUTHORIZED-SUCCESS",
    execution_generation=generation_a,
)

print("COMPLETION:", completion)

state = load_state()
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
)

# Completion must not manufacture success after revocation.
assert action["status"] != "executed"
assert action.get("execution_result") != "UNAUTHORIZED-SUCCESS"

print("PASS: revoked worker could not manufacture durable success.")

print()
print("8. VERIFY REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert file_a.exists()
assert file_b.exists()

print("No filesystem mutation occurred after revocation.")
print("PASS")

print()
print("9. VERIFY RETRY CANNOT BYPASS REVOCATION:")

retry = retry_failed_action(ACTION)

print("RETRY:", retry)

state = load_state()
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| retry_count =", action["retry_count"],
)

# A rejected action must not silently become retry-authorized.
assert retry["status"] == "blocked"
assert action["retry_count"] == 0

print("PASS: revocation cannot be bypassed through retry.")

print()
print("10. FINAL DURABLE STATE:")

state = load_state()
action = state["actions"][0]

print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
    "| generation =", action.get("execution_generation"),
)

assert action["status"] == "rejected"
assert action["retry_count"] == 0

print("PASS")

print()
print("11. FINAL REAL-WORLD STATE:")

print("A exists:", file_a.exists())
print("B exists:", file_b.exists())

assert file_a.exists()
assert file_b.exists()

print("PASS")

print()
print("12. AUTHORIZATION-REVOCATION INVARIANTS:")

print("ACTIVE EXECUTION WAS INITIALLY AUTHORIZED")
print("AUTHORIZATION WAS REVOKED DURING EXECUTION")
print("REVOKED WORKER COULD NOT MUTATE THE WORLD")
print("REVOKED WORKER COULD NOT MANUFACTURE SUCCESS")
print("REVOCATION REMAINED DURABLE")
print("RETRY COULD NOT BYPASS REVOCATION")
print("REAL-WORLD STATE REMAINED UNCHANGED")
print("NO UNAUTHORIZED SUCCESS WAS RECORDED")

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
