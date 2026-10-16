import json
import multiprocessing
from pathlib import Path

from judgment.lifecycle import retry_failed_action
from judgment.audit import load_audit

STATE_PATH = Path(r"state\latest.json")
ACTION = "free-disk-space"

def attempt_retry(_unused=None):
    result = retry_failed_action(ACTION)
    print("WORKER:", result, flush=True)
    return result

def main():
    print("=== CONCURRENT RETRY → EXACTLY-ONCE BUDGET CONSUMPTION INVARIANT TEST ===")

    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    target = next(a for a in state["actions"] if a.get("action") == ACTION)

    target["status"] = "failed"
    target["retry_count"] = 0
    target["max_retries"] = 2
    target["escalation_required"] = False
    target["execution_result"] = "concurrent-retry-test"

    STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    before = load_audit()

    print()
    print("1. INITIAL FAILED STATE:")
    print(
        ACTION,
        "| status =", target["status"],
        "| retry_count =", target["retry_count"],
        "| escalation =", target["escalation_required"],
    )
    print("PASS")

    print()
    print("2. LAUNCH TWO CONCURRENT RETRIES:")

    with multiprocessing.Pool(processes=2) as pool:
        results = pool.map(attempt_retry, [None, None])

    print()
    print("WORKER RESULTS:")
    for result in results:
        print(result)

    approved = [
        result
        for result in results
        if result.get("status") == "approved"
    ]

    blocked = [
        result
        for result in results
        if result.get("status") == "blocked"
    ]

    print()
    print("3. CONCURRENT RESULT INVARIANT:")
    print("APPROVED:", len(approved))
    print("BLOCKED:", len(blocked))

    assert len(approved) == 1
    assert len(blocked) == 1

    print("Exactly one retry authorization succeeded.")
    print("Exactly one concurrent attempt was rejected.")
    print("PASS")

    print()
    print("4. DURABLE STATE:")

    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    target = next(
        a for a in state["actions"]
        if a.get("action") == ACTION
    )

    print(
        ACTION,
        "| status =", target["status"],
        "| retry_count =", target["retry_count"],
        "| max_retries =", target["max_retries"],
        "| escalation =", target["escalation_required"],
    )

    assert target["retry_count"] == 1
    assert target["status"] == "approved"
    assert target["escalation_required"] is False

    print("Retry budget consumed exactly once.")
    print("PASS")

    print()
    print("5. AUDIT CHECK:")

    after = load_audit()

    events = [
        event
        for event in after[len(before):]
        if event.get("action") == ACTION
    ]

    retry_events = [
        event
        for event in events
        if event.get("event") == "retry-approved"
    ]

    for event in events:
        print(
            event.get("event"),
            "|",
            event.get("status"),
            "|",
            event.get("result"),
            "| retry_count =",
            event.get("retry_count"),
        )

    assert len(retry_events) == 1
    assert retry_events[0]["retry_count"] == 1

    print("Exactly one retry-approved audit event exists.")
    print("PASS")

    print()
    print("6. FINAL CONCURRENCY INVARIANT:")
    print("TWO RETRY REQUESTS WERE ISSUED")
    print("ONLY ONE RETRY SLOT WAS CONSUMED")
    print("DURABLE RETRY COUNT = 1")
    print("ONLY ONE RETRY-APPROVED AUDIT EVENT EXISTS")
    print("NO DOUBLE-CONSUMPTION OCCURRED")
    print("RESULT: PASS")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
