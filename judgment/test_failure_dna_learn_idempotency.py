from backend.core.cognitive.failure_dna import FailureDNAEngine

def main():
    print("=== FAILUREDNA LEARN IDEMPOTENCY REGRESSION ===")

    engine = FailureDNAEngine()

    print("\n1. RECORDING ONE EVENT:")
    result = engine.record_failure(
        "PROCESS_CRASH",
        "Idempotency regression crash event",
        severity="HIGH",
    )

    print("record_failure() return value:", result)

    history = engine.get_failure_history()
    assert history, "record_failure() did not create a history entry."

    event = history[0]

    print("event_id:", event.event_id)

    matching_after_record = [
        e for e in history
        if getattr(e, "event_id", None) == event.event_id
    ]

    print("matching occurrences:", len(matching_after_record))

    assert len(matching_after_record) == 1
    print("PASS")

    print("\n2. FIRST learn(event):")

    before_first_learn = len([
        e for e in engine.get_failure_history()
        if getattr(e, "event_id", None) == event.event_id
    ])

    engine.learn(event)

    after_first_learn = len([
        e for e in engine.get_failure_history()
        if getattr(e, "event_id", None) == event.event_id
    ])

    print("before learn():", before_first_learn)
    print("after learn():", after_first_learn)

    assert after_first_learn == before_first_learn
    print("PASS: already-recorded event was not duplicated.")

    print("\n3. SECOND learn(event):")

    engine.learn(event)

    after_second_learn = len([
        e for e in engine.get_failure_history()
        if getattr(e, "event_id", None) == event.event_id
    ])

    print("after second learn():", after_second_learn)

    assert after_second_learn == 1
    print("PASS: repeated learn() remains idempotent.")

    print("\n4. VERIFY EVENT IDENTITY:")

    ids = [
        e.event_id
        for e in engine.get_failure_history()
        if getattr(e, "event_id", None) == event.event_id
    ]

    print("matching IDs:", ids)

    assert ids == [event.event_id]
    print("PASS")

    print("\n5. FINAL INVARIANTS:")
    print("ONE EVENT RECORDED:", len(ids) == 1)
    print("FIRST learn() DID NOT DUPLICATE:", after_first_learn == 1)
    print("SECOND learn() DID NOT DUPLICATE:", after_second_learn == 1)
    print("EVENT IDENTITY PRESERVED:", ids == [event.event_id])

    assert len(ids) == 1
    assert after_first_learn == 1
    assert after_second_learn == 1

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
