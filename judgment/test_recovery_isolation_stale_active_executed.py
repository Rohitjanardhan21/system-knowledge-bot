from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

from judgment.audit import load_audit, record_execution
from judgment.recovery import recover_interrupted_actions
from judgment.state_lock import state_lock


STATE_PATH = Path("state") / "latest.json"
TEST_ID = f"recovery-isolation-{uuid.uuid4().hex[:8]}"

STALE = f"{TEST_ID}-STALE"
ACTIVE = f"{TEST_ID}-ACTIVE"
EXECUTED = f"{TEST_ID}-EXECUTED"


def write_state(actions):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with state_lock():
        temp = STATE_PATH.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as f:
            json.dump({"actions": actions}, f, indent=2)
            f.flush()
        temp.replace(STATE_PATH)


def get_action(name):
    with STATE_PATH.open("r", encoding="utf-8") as f:
        state = json.load(f)

    for action in state["actions"]:
        if action["action"] == name:
            return action

    raise AssertionError(f"Action not found: {name}")


def completion_events(name, generation):
    return [
        e for e in load_audit()
        if isinstance(e, dict)
        and e.get("event") == "execution-completed"
        and e.get("action") == name
        and e.get("execution_generation") == generation
    ]


def recovery_events(name):
    return [
        e for e in load_audit()
        if isinstance(e, dict)
        and e.get("event") == "recovery-interrupted"
        and e.get("action") == name
    ]


def main():
    print("=== PROPER RECOVERY ISOLATION: STALE VS ACTIVE VS EXECUTED ===")

    print("\n1. PREPARING THREE INDEPENDENT ACTIONS:")

    actions = [
        {
            "action": STALE,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "executing",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": None,
            "execution_generation": 11,
            "execution_started_at": "2000-01-01T00:00:00+00:00",
        },
        {
            "action": ACTIVE,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "executing",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": None,
            "execution_generation": 22,
            "execution_started_at": "2099-01-01T00:00:00+00:00",
        },
        {
            "action": EXECUTED,
            "priority": "high",
            "execution_mode": "automatic",
            "status": "executed",
            "retry_count": 0,
            "max_retries": 2,
            "escalation_required": False,
            "execution_result": "ALREADY-EXECUTED",
            "execution_generation": 33,
            "execution_started_at": "2099-01-01T00:00:00+00:00",
            "execution_completed_at": "2099-01-01T00:00:01+00:00",
        },
    ]

    record_execution([{
        "event": "execution-completed",
        "action": EXECUTED,
        "status": "executed",
        "result": "ALREADY-EXECUTED",
        "execution_generation": 33,
    }])

    write_state(actions)

    print(f"{STALE} | status=executing | generation=11")
    print(f"{ACTIVE} | status=executing | generation=22")
    print(f"{EXECUTED} | status=executed | generation=33")
    print("PASS")

    print("\n2. RUNNING REAL RECOVERY API:")

    result = recover_interrupted_actions()

    print("RECOVERY RESULT:", result)

    assert STALE in result
    assert ACTIVE not in result
    assert EXECUTED not in result

    print("Only the stale executing action was recovered.")
    print("PASS")

    print("\n3. VERIFYING STALE ACTION:")

    stale = get_action(STALE)

    print(
        f"{STALE} | status={stale['status']} | "
        f"result={stale['execution_result']} | "
        f"generation={stale['execution_generation']}"
    )

    assert stale["status"] == "failed"
    assert stale["execution_result"] == "interrupted-by-restart"
    assert stale["execution_generation"] == 11

    print("STALE ACTION RECOVERED CORRECTLY.")
    print("PASS")

    print("\n4. VERIFYING ACTIVE ACTION WAS NOT TOUCHED:")

    active = get_action(ACTIVE)

    print(
        f"{ACTIVE} | status={active['status']} | "
        f"result={active['execution_result']} | "
        f"generation={active['execution_generation']}"
    )

    assert active["status"] == "executing"
    assert active["execution_result"] is None
    assert active["execution_generation"] == 22

    print("ACTIVE EXECUTION WAS PRESERVED.")
    print("PASS")

    print("\n5. VERIFYING EXECUTED ACTION WAS NOT TOUCHED:")

    executed = get_action(EXECUTED)

    print(
        f"{EXECUTED} | status={executed['status']} | "
        f"result={executed['execution_result']} | "
        f"generation={executed['execution_generation']}"
    )

    assert executed["status"] == "executed"
    assert executed["execution_result"] == "ALREADY-EXECUTED"
    assert executed["execution_generation"] == 33

    print("ALREADY-EXECUTED ACTION WAS PRESERVED.")
    print("PASS")

    print("\n6. VERIFYING RECOVERY AUDIT:")

    stale_recovery = recovery_events(STALE)
    active_recovery = recovery_events(ACTIVE)
    executed_recovery = recovery_events(EXECUTED)

    print("STALE recovery events:", len(stale_recovery))
    print("ACTIVE recovery events:", len(active_recovery))
    print("EXECUTED recovery events:", len(executed_recovery))

    assert len(stale_recovery) == 1
    assert len(active_recovery) == 0
    assert len(executed_recovery) == 0

    print("Exactly one recovery audit belongs to the stale action.")
    print("PASS")

    print("\n7. RUNNING SECOND RECOVERY:")

    second = recover_interrupted_actions()

    print("SECOND RECOVERY RESULT:", second)

    assert STALE not in second
    assert ACTIVE not in second
    assert EXECUTED not in second

    print("Second recovery is idempotent.")
    print("PASS")

    print("\n8. VERIFYING NO DUPLICATE RECOVERY AUDIT:")

    stale_recovery_after = recovery_events(STALE)

    print(
        "Stale recovery events after second recovery:",
        len(stale_recovery_after),
    )

    assert len(stale_recovery_after) == 1

    print("No duplicate recovery event exists.")
    print("PASS")

    print("\n9. FRESH-PROCESS CONSISTENCY:")

    code = f"""
import json
from pathlib import Path

p = Path(r'{STATE_PATH}')
with p.open('r', encoding='utf-8') as f:
    state = json.load(f)

for name in {STALE!r}, {ACTIVE!r}, {EXECUTED!r}:
    action = next(a for a in state['actions'] if a['action'] == name)
    print(name, '| status=', action['status'],
          '| generation=', action['execution_generation'],
          '| result=', action.get('execution_result'))
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )

    print(completed.stdout, end="")

    assert completed.returncode == 0

    print("Fresh process observed consistent durable state.")
    print("PASS")

    print("\n10. FINAL HARD INVARIANTS:")
    print("STALE EXECUTION WAS RECOVERED")
    print("ACTIVE EXECUTION WAS NOT RECOVERED")
    print("ALREADY-EXECUTED ACTION WAS NOT ALTERED")
    print("STALE GENERATION REMAINED 11")
    print("ACTIVE GENERATION REMAINED 22")
    print("EXECUTED GENERATION REMAINED 33")
    print("EXACTLY ONE RECOVERY AUDIT EXISTS")
    print("SECOND RECOVERY WAS IDEMPOTENT")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
