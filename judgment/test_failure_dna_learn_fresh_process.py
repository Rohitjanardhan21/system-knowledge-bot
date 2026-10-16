from backend.core.cognitive.failure_dna import FailureDNAEngine

def main():
    print("=== FAILUREDNA LEARN FRESH-PROCESS PERSISTENCE REGRESSION ===")

    print("\n1. CREATING FIRST ENGINE:")
    engine1 = FailureDNAEngine()

    engine1.record_failure(
        "PROCESS_CRASH",
        "Fresh-process persistence regression event",
        severity="HIGH",
    )

    history1 = engine1.get_failure_history()
    assert history1

    event = history1[0]
    event_id = event.event_id

    print("event_id:", event_id)
    print("matching events:", sum(
        1 for e in history1
        if getattr(e, "event_id", None) == event_id
    ))

    print("PASS")

    print("\n2. CALLING learn() ON ALREADY-PERSISTED EVENT:")
    engine1.learn(event)

    history1_after_learn = engine1.get_failure_history()

    count_after_learn = sum(
        1 for e in history1_after_learn
        if getattr(e, "event_id", None) == event_id
    )

    print("matching events after learn():", count_after_learn)

    assert count_after_learn == 1
    print("PASS")

    print("\n3. CREATING COMPLETELY FRESH ENGINE:")
    engine2 = FailureDNAEngine()

    history2 = engine2.get_failure_history()

    matching_fresh = [
        e for e in history2
        if getattr(e, "event_id", None) == event_id
    ]

    print("fresh engine matching events:", len(matching_fresh))

    assert len(matching_fresh) == 1
    print("PASS: event survived fresh-engine reload.")

    print("\n4. VERIFY EVENT CONTENT:")
    fresh_event = matching_fresh[0]

    print("event_id:", fresh_event.event_id)
    print("event_type:", fresh_event.event_type)
    print("description:", fresh_event.description)
    print("severity:", fresh_event.severity)

    assert fresh_event.event_id == event_id
    assert fresh_event.event_type == "PROCESS_CRASH"
    assert fresh_event.description == "Fresh-process persistence regression event"
    assert fresh_event.severity == "HIGH"

    print("PASS")

    print("\n5. VERIFY SECOND FRESH ENGINE:")
    engine3 = FailureDNAEngine()

    history3 = engine3.get_failure_history()

    matching_third = [
        e for e in history3
        if getattr(e, "event_id", None) == event_id
    ]

    print("third engine matching events:", len(matching_third))

    assert len(matching_third) == 1
    print("PASS")

    print("\n6. FINAL INVARIANTS:")
    print("ORIGINAL ENGINE HAS ONE EVENT:", count_after_learn == 1)
    print("FRESH ENGINE HAS ONE EVENT:", len(matching_fresh) == 1)
    print("SECOND FRESH ENGINE HAS ONE EVENT:", len(matching_third) == 1)
    print("EVENT ID STABLE:", matching_fresh[0].event_id == event_id)
    print("EVENT CONTENT PRESERVED:", (
        fresh_event.event_type == "PROCESS_CRASH"
        and fresh_event.description == "Fresh-process persistence regression event"
        and fresh_event.severity == "HIGH"
    ))

    assert count_after_learn == 1
    assert len(matching_fresh) == 1
    assert len(matching_third) == 1

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
