from pathlib import Path
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

STATE_PATH = Path("state/latest.json")
AUDIT_PATH = Path("state/audit.json")
AUDIT_TMP = Path("state/audit.tmp")

ACTION = f"recovery-reconcile-concurrency-{os.getpid()}"
GENERATION = 1
WORKERS = 8


def write_state():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "actions": [{
            "action": ACTION,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "executed",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": "RECOVERY-RECONCILIATION-RACE",
            "execution_generation": GENERATION,
            "execution_started_at": datetime.now(timezone.utc).isoformat(),
            "execution_completed_at": datetime.now(timezone.utc).isoformat(),
        }]
    }

    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def write_empty_audit():
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if AUDIT_TMP.exists():
        AUDIT_TMP.unlink()

    AUDIT_PATH.write_text("[]", encoding="utf-8")


def load_audit():
    try:
        return json.loads(
            AUDIT_PATH.read_text(encoding="utf-8")
        )
    except Exception:
        return []


print()
print("=== RECOVERY AUDIT RECONCILIATION CONCURRENCY TEST ===")
print()

print("1. PREPARING EXECUTED STATE WITH MISSING AUDIT:")
write_state()
write_empty_audit()

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = state["actions"][0]

print(
    f"{action['action']} | "
    f"status = {action['status']} | "
    f"generation = {action['execution_generation']}"
)

matches = [
    e for e in load_audit()
    if isinstance(e, dict)
    and e.get("event") == "execution-completed"
    and e.get("action") == ACTION
    and e.get("execution_generation") == GENERATION
]

assert action["status"] == "executed"
assert len(matches) == 0

print("Completion audit events: 0")
print("PASS")
print()


print("2. STARTING CONCURRENT RECOVERY PROCESSES:")

command = (
    "from judgment.recovery import recover_interrupted_actions; "
    "print(recover_interrupted_actions())"
)

processes = []

for i in range(WORKERS):
    p = subprocess.Popen(
        [sys.executable, "-c", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    processes.append((i + 1, p))

results = []

for worker_id, p in processes:
    stdout, stderr = p.communicate()
    results.append((worker_id, p.returncode, stdout.strip(), stderr.strip()))

for worker_id, code, stdout, stderr in results:
    print(
        f"RECOVERY WORKER {worker_id}: "
        f"exitcode={code} | result={stdout}"
    )

assert all(code == 0 for _, code, _, _ in results)

print("All concurrent recovery processes completed.")
print("PASS")
print()


print("3. CHECKING FIRST-WAVE RECONCILIATION:")

audit = load_audit()

matches = [
    e for e in audit
    if isinstance(e, dict)
    and e.get("event") == "execution-completed"
    and e.get("action") == ACTION
    and e.get("execution_generation") == GENERATION
]

print(f"Matching completion events: {len(matches)}")

assert len(matches) == 1

event = matches[0]

assert event.get("status") == "executed"
assert event.get("result") == "RECOVERY-RECONCILIATION-RACE"
assert event.get("execution_generation") == GENERATION
assert event.get("recovered") is True

print("Exactly ONE recovery completion event exists.")
print("Generation identity is correct.")
print("PASS")
print()


print("4. VERIFYING DURABLE STATE:")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = next(
    a for a in state["actions"]
    if a.get("action") == ACTION
)

print(
    f"{action['action']} | "
    f"status = {action['status']} | "
    f"result = {action['execution_result']} | "
    f"generation = {action['execution_generation']}"
)

assert action["status"] == "executed"
assert action["execution_generation"] == GENERATION
assert action["execution_result"] == "RECOVERY-RECONCILIATION-RACE"

print("Executed state was preserved.")
print("PASS")
print()


print("5. SECOND CONCURRENT RECOVERY WAVE:")

processes = []

for i in range(WORKERS):
    p = subprocess.Popen(
        [sys.executable, "-c", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    processes.append((i + 1, p))

second_results = []

for worker_id, p in processes:
    stdout, stderr = p.communicate()
    second_results.append(
        (worker_id, p.returncode, stdout.strip(), stderr.strip())
    )

for worker_id, code, stdout, stderr in second_results:
    print(
        f"RECOVERY-2 WORKER {worker_id}: "
        f"exitcode={code} | result={stdout}"
    )

assert all(code == 0 for _, code, _, _ in second_results)

print("Second recovery wave completed.")
print("PASS")
print()


print("6. FINAL DUPLICATION CHECK:")

audit = load_audit()

matches = [
    e for e in audit
    if isinstance(e, dict)
    and e.get("event") == "execution-completed"
    and e.get("action") == ACTION
    and e.get("execution_generation") == GENERATION
]

print(f"Final matching completion events: {len(matches)}")

assert len(matches) == 1

print("No duplicate reconciliation event was created.")
print("PASS")
print()


print("7. FINAL FRESH-PROCESS CONSISTENCY:")

fresh = subprocess.run(
    [
        sys.executable,
        "-c",
        (
            "import json; "
            "from pathlib import Path; "
            "s=json.loads(Path('state/latest.json').read_text()); "
            f"a=next(x for x in s['actions'] if x.get('action') == {ACTION!r}); "
            "print(a)"
        ),
    ],
    capture_output=True,
    text=True,
)

print(fresh.stdout.strip())

assert fresh.returncode == 0
assert "'status': 'executed'" in fresh.stdout
assert f"'execution_generation': {GENERATION}" in fresh.stdout

print("Fresh process observed the same durable executed state.")
print("PASS")
print()


print("8. FINAL INVARIANTS:")
print("CONCURRENT RECOVERY PROCESSES COMPLETED")
print("EXACTLY ONE RECONCILIATION WON")
print("NO DUPLICATE COMPLETION EVENT EXISTS")
print("RECOVERED EVENT HAS CORRECT GENERATION")
print("EXECUTED STATE WAS NEVER ALTERED")
print("SECOND RECOVERY WAVE WAS IDEMPOTENT")
print("FRESH PROCESS OBSERVED CONSISTENT STATE")
print()
print("RESULT: PASS")
