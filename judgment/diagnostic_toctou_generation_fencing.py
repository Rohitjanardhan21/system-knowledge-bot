import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from judgment.audit import load_audit
from judgment.execution import execute_action
from judgment.lifecycle import (
    complete_execution,
    retry_failed_action,
    run_execution_side_effect,
)
from judgment.recovery import STATE_PATH, recover_interrupted_actions


ACTION = "free-disk-space"
SANDBOX = Path("state") / "toctou_fencing_sandbox"
SANDBOX.mkdir(parents=True, exist_ok=True)

file_a = SANDBOX / "worker_a.tmp"
file_b = SANDBOX / "worker_b.tmp"

for target_file in (file_a, file_b):
    target_file.write_text("temporary data", encoding="utf-8")

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
STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

before = load_audit()

print("=== TOCTOU GENERATION-FENCING / SIDE-EFFECT RACE TEST ===")
print()
print("1. INITIAL STATE:")
print("A:", file_a.exists())
print("B:", file_b.exists())
assert file_a.exists() and file_b.exists()
print("PASS")

print()
print("2. WORKER A STARTS:")
start_a = execute_action(ACTION)
print("WORKER A:", start_a)
assert start_a["status"] == "executing"
generation_a = start_a["execution_generation"]
print("Generation A:", generation_a)
print("PASS")

# Model an action that was left executing by a process crash before the
# side-effect race begins, so recovery sees it as stale after the lock clears.
state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
state["actions"][0]["execution_started_at"] = (
    datetime.now(timezone.utc) - timedelta(minutes=10)
).isoformat()
STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

print()
print("3. WORKER A PAUSES INSIDE SIDE-EFFECT ADMISSION:")
admission_checked = threading.Event()
resume_worker = threading.Event()
worker_a_result = {}


def worker_a_side_effect():
    def mutate_file_a():
        admission_checked.set()
        if not resume_worker.wait(timeout=10):
            raise TimeoutError("Worker A was not resumed.")
        file_a.unlink()
        return "worker-a-deleted-file-a"

    try:
        worker_a_result["result"] = run_execution_side_effect(
            ACTION,
            generation_a,
            mutate_file_a,
        )
    except Exception as exc:
        worker_a_result["error"] = repr(exc)


thread_a = threading.Thread(target=worker_a_side_effect, name="worker-a")
thread_a.start()
assert admission_checked.wait(timeout=10)
print("Worker A holds the lifecycle lock before its filesystem mutation.")
print("PASS")

print()
print("4. RECOVERY RACES WITH WORKER A:")
recovery_started = threading.Event()
recovery_finished = threading.Event()
recovery_result = {}


def recovery_worker():
    recovery_started.set()
    try:
        recovery_result["actions"] = recover_interrupted_actions()
    except Exception as exc:
        recovery_result["error"] = repr(exc)
    finally:
        recovery_finished.set()


thread_recovery = threading.Thread(
    target=recovery_worker,
    name="recovery-worker",
)
thread_recovery.start()
assert recovery_started.wait(timeout=10)
assert not recovery_finished.wait(timeout=0.1)
print("Recovery cannot pass the state lock while Worker A's operation is active.")

resume_worker.set()
thread_a.join(timeout=10)
thread_recovery.join(timeout=10)
assert not thread_a.is_alive()
assert not thread_recovery.is_alive()
assert "error" not in worker_a_result
assert "error" not in recovery_result
assert worker_a_result["result"]["status"] == "allowed"
assert not file_a.exists()

recovered = recovery_result["actions"]
print("RECOVERED:", recovered)
assert ACTION in recovered

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]
print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
)
assert action["status"] == "failed"
assert action["execution_result"] == "interrupted-by-restart"
print("PASS")

print()
print("5. WORKER B RETRIES AND STARTS:")
retry = retry_failed_action(ACTION)
print("RETRY:", retry)
assert retry["status"] == "approved"
assert retry["retry_count"] == 1

start_b = execute_action(ACTION)
print("WORKER B:", start_b)
assert start_b["status"] == "executing"
generation_b = start_b["execution_generation"]
assert generation_b != generation_a
print("Generation A:", generation_a, "| Generation B:", generation_b)
print("PASS")

print()
print("6. WORKER A'S POST-RECOVERY SIDE EFFECT IS BLOCKED:")
stale_side_effect = run_execution_side_effect(
    ACTION,
    generation_a,
    file_b.unlink,
)
print("STALE WORKER A:", stale_side_effect)
assert stale_side_effect["status"] == "blocked"
assert file_b.exists()
print("PASS")

print()
print("7. WORKER B COMPLETES ITS SIDE EFFECT:")
side_effect_b = run_execution_side_effect(
    ACTION,
    generation_b,
    file_b.unlink,
)
print("WORKER B SIDE EFFECT:", side_effect_b)
assert side_effect_b["status"] == "allowed"
assert not file_b.exists()

completion_b = complete_execution(
    ACTION,
    result="WORKER-B-SUCCESS",
    execution_generation=generation_b,
)
print("WORKER B COMPLETION:", completion_b)
assert completion_b["status"] == "executed"
print("PASS")

print()
print("8. FINAL STATE AND AUDIT:")
state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]
print(
    ACTION,
    "| status =", action["status"],
    "| result =", action.get("execution_result"),
    "| retry_count =", action["retry_count"],
)
assert action["status"] == "executed"
assert action["execution_result"] == "WORKER-B-SUCCESS"
assert action["retry_count"] == 1
assert not file_a.exists() and not file_b.exists()

after = load_audit()
events = [
    event for event in after[len(before):]
    if event.get("action") == ACTION
]
for event in events:
    print(
        event.get("event"),
        "|", event.get("status"),
        "|", event.get("result"),
    )

print("TOCTOU SIDE-EFFECT ADMISSION WAS ATOMIC WITH RECOVERY")
print("STALE GENERATION COULD NOT MUTATE THE FILESYSTEM")
print("WORKER B COMPLETED THE CURRENT GENERATION")
print("RESULT: PASS")

for target_file in (file_a, file_b):
    if target_file.exists():
        target_file.unlink()
if SANDBOX.exists():
    try:
        SANDBOX.rmdir()
    except OSError:
        pass