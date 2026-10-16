from backend.core.cognitive.failure_dna import FailureDNAEngine

def main():
    print("=== FAILUREDNA NEW EVENT LEARNING REGRESSION ===")

    engine = FailureDNAEngine()

    print("\n1. RECORDING FIRST EVENT:")
    engine.record_failure(
        "PROCESS_CRASH",
        "First crash event for learning regression",
        severity="HIGH",
    )

    history = engine.get_failure_history()
    event1 = history[0]

    print("event1:", event1.event_id)
    print("history occurrences:", sum(
        1 for e in history
        if getattr(e, "event_id", None) == event1.event_id
    ))

    print("PASS")

    print("\n2. CREATING A GENUINELY NEW EVENT:")
    engine.record_failure(
        "PROCESS_CRASH",
        "Second distinct crash event for learning regression",
        severity="HIGH",
    )

    history = engine.get_failure_history()

    event2 = next(
        e for e in history
        if getattr(e, "event_id", None) != event1.event_id
    )

    print("event2:", event2.event_id)

    assert event2.event_id != event1.event_id
    print("PASS: event has a distinct identity.")

    print("\n3. LEARNING THE NEW EVENT:")
    before = len([
        e for e in engine.get_failure_history()
        if getattr(e, "event_id", None) == event2.event_id
    ])

    engine.learn(event2)

    after = len([
        e for e in engine.get_failure_history()
        if getattr(e, "event_id", None) == event2.event_id
    ])

    print("before learn():", before)
    print("after learn():", after)

    assert before == 1
    assert after == 1
    print("PASS: new event was accepted without duplication.")

    print("\n4. VERIFY SECOND learn() IS STILL IDEMPOTENT:")
    engine.learn(event2)

    final_count = len([
        e for e in engine.get_failure_history()
        if getattr(e, "event_id", None) == event2.event_id
    ])

    print("after second learn():", final_count)

    assert final_count == 1
    print("PASS")

    print("\n5. VERIFY BOTH EVENTS EXIST:")
    final_history = engine.get_failure_history()

    event1_count = sum(
        1 for e in final_history
        if getattr(e, "event_id", None) == event1.event_id
    )

    event2_count = sum(
        1 for e in final_history
        if getattr(e, "event_id", None) == event2.event_id
    )

    print("event1 occurrences:", event1_count)
    print("event2 occurrences:", event2_count)

    assert event1_count == 1
    assert event2_count == 1
    assert event1.event_id != event2.event_id

    print("PASS")

    print("\n6. FINAL INVARIANTS:")
    print("FIRST EVENT PRESERVED:", event1_count == 1)
    print("NEW EVENT PRESERVED:", event2_count == 1)
    print("EVENT IDs DISTINCT:", event1.event_id != event2.event_id)
    print("NEW EVENT learn() ACCEPTED:", after == 1)
    print("REPEATED learn() IDEMPOTENT:", final_count == 1)

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
