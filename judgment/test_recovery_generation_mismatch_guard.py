import json
from pathlib import Path
from judgment.audit import load_audit
from judgment.recovery import recover_interrupted_actions

STATE_PATH = Path("state/latest.json")
ACTION = "recovery-generation-mismatch-guard"

def load_state():
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))

def save_state(state):
    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

def matching(events, generation):
    return [
        e for e in events
        if isinstance(e, dict)
        and e.get("event") == "execution-completed"
        and e.get("action") == ACTION
        and e.get("execution_generation") == generation
    ]

def main():
    print("=== RECOVERY GENERATION-MISMATCH GUARD TEST ===")

    # ---------------------------------------------------------
    # 1. CLEAN STATE
    # ---------------------------------------------------------
    print("\n1. PREPARING EXECUTED GENERATION 2 WITH STALE GENERATION 1 AUDIT:")

    state = load_state()
    state["actions"] = [
        a for a in state.get("actions", [])
        if not (
            isinstance(a, dict)
            and a.get("action") == ACTION
        )
    ]

    state["actions"].append({
        "action": ACTION,
        "priority": "high",
        "execution_mode": "automatic",
        "status": "executed",
        "retry_count": 0,
        "max_retries": 2,
        "escalation_required": False,
        "execution_result": "CURRENT-GENERATION-2",
        "execution_generation": 2,
        "execution_started_at": "2026-10-05T06:00:00+00:00",
        "execution_completed_at": "2026-10-05T06:00:01+00:00",
    })

    save_state(state)

    print(
        f"{ACTION} | status=executed | generation=2"
    )
    print("PASS")

    # ---------------------------------------------------------
    # 2. INSTALL STALE AUDIT ONLY
    # ---------------------------------------------------------
    print("\n2. INSTALLING STALE COMPLETION AUDIT FOR GENERATION 1:")

    audit_path = Path("state") / "audit.json"

    stale_event = {
        "timestamp": "2026-10-05T05:59:00+00:00",
        "event": "execution-completed",
        "action": ACTION,
        "status": "executed",
        "result": "OLD-GENERATION-1",
        "execution_generation": 1,
    }

    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps([stale_event], indent=2),
        encoding="utf-8",
    )

    events = load_audit()
    stale = matching(events, 1)
    current = matching(events, 2)

    print(f"Generation 1 completion events: {len(stale)}")
    print(f"Generation 2 completion events: {len(current)}")

    assert len(stale) == 1
    assert len(current) == 0

    print("Stale audit exists; current generation is unaudited.")
    print("PASS")

    # ---------------------------------------------------------
    # 3. RUN RECOVERY
    # ---------------------------------------------------------
    print("\n3. RUNNING FRESH-PROCESS RECOVERY:")

    recovered = recover_interrupted_actions()

    print(f"RECOVERY RESULT: {recovered}")

    # The action is already EXECUTED, so recovery should reconcile
    # the missing audit without changing lifecycle state.
    assert ACTION in recovered

    print("Recovery detected the missing current-generation audit.")
    print("PASS")

    # ---------------------------------------------------------
    # 4. VERIFY BOTH GENERATIONS
    # ---------------------------------------------------------
    print("\n4. VERIFYING GENERATION-SPECIFIC AUDIT:")

    events = load_audit()

    stale = matching(events, 1)
    current = matching(events, 2)

    print(f"Generation 1 completion events: {len(stale)}")
    print(f"Generation 2 completion events: {len(current)}")

    assert len(stale) == 1
    assert len(current) == 1

    assert current[0]["execution_generation"] == 2
    assert current[0]["result"] != "OLD-GENERATION-1"

    print("Stale generation was NOT treated as current completion.")
    print("Exactly one current-generation reconciliation exists.")
    print("PASS")

    # ---------------------------------------------------------
    # 5. VERIFY DURABLE STATE
    # ---------------------------------------------------------
    print("\n5. VERIFYING DURABLE LIFECYCLE STATE:")

    state = load_state()

    target = next(
        a for a in state["actions"]
        if a.get("action") == ACTION
    )

    print(
        f"{ACTION} | status={target.get('status')} "
        f"| result={target.get('execution_result')} "
        f"| generation={target.get('execution_generation')}"
    )

    assert target["status"] == "executed"
    assert target["execution_generation"] == 2
    assert target["execution_result"] == "CURRENT-GENERATION-2"

    print("Executed state and generation were preserved.")
    print("PASS")

    # ---------------------------------------------------------
    # 6. SECOND RECOVERY MUST BE IDEMPOTENT
    # ---------------------------------------------------------
    print("\n6. SECOND RECOVERY / DUPLICATION CHECK:")

    second = recover_interrupted_actions()

    print(f"SECOND RECOVERY RESULT: {second}")

    assert second == []

    events = load_audit()
    current = matching(events, 2)

    print(f"Generation 2 completion events: {len(current)}")

    assert len(current) == 1

    print("No duplicate current-generation completion was created.")
    print("PASS")

    # ---------------------------------------------------------
    # 7. FRESH PROCESS CONSISTENCY
    # ---------------------------------------------------------
    print("\n7. FRESH-PROCESS CONSISTENCY:")

    state = load_state()
    target = next(
        a for a in state["actions"]
        if a.get("action") == ACTION
    )

    events = load_audit()
    current = matching(events, 2)

    print(target)
    print(f"Current-generation completion events: {len(current)}")

    assert target["status"] == "executed"
    assert target["execution_generation"] == 2
    assert len(current) == 1

    print("Fresh process observes consistent state/audit.")
    print("PASS")

    # ---------------------------------------------------------
    # 8. FINAL INVARIANTS
    # ---------------------------------------------------------
    print("\n8. FINAL GENERATION-MISMATCH INVARIANTS:")

    print("STALE GENERATION 1 AUDIT WAS NOT ACCEPTED AS CURRENT")
    print("CURRENT GENERATION 2 WAS CORRECTLY RECONCILED")
    print("EXACTLY ONE CURRENT-GENERATION COMPLETION EXISTS")
    print("STALE AUDIT WAS PRESERVED")
    print("EXECUTED STATE WAS NEVER ALTERED")
    print("EXECUTION GENERATION REMAINED 2")
    print("SECOND RECOVERY WAS IDEMPOTENT")
    print("NO DUPLICATE COMPLETION WAS CREATED")
    print("FRESH PROCESS OBSERVED CONSISTENT STATE/AUDIT")

    print("\nRESULT: PASS")

if __name__ == "__main__":
    main()
