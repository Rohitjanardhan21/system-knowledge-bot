import time
import uuid

from backend.core.cognitive.failure_dna import FailureDNAEngine, FailureEvent

def main():
    print("=== FAILUREDNA PATTERN LEARNING IDEMPOTENCY REGRESSION ===")

    engine = FailureDNAEngine()

    print("\n1. FINDING CRASH PATTERN:")
    crash_pattern = engine._patterns.get("dna_CRASH")

    assert crash_pattern is not None, "dna_CRASH pattern does not exist."

    initial_seen = crash_pattern.seen_count

    print("Initial CRASH seen_count:", initial_seen)
    print("Initial CRASH confidence:", crash_pattern.confidence)
    print("PASS")

    print("\n2. CREATING A GENUINELY NEW FAILURE EVENT:")

    event = FailureEvent(
        event_id=(
            "PROCESS_CRASH_PATTERN_IDEMPOTENCY_TEST_"
            f"{uuid.uuid4().hex}"
        ),
        event_type="CRASH",
        timestamp=time.time(),
        description=(
            "Pattern learning idempotency regression "
            f"{uuid.uuid4().hex}"
        ),
        pre_snapshot=[
            {
                "cpu": 25.0 + i * 0.1,
                "mem": 40.0,
                "disk": 35.0,
                "net": 10.0,
                "anomaly": 0.1,
            }
            for i in range(70)
        ],
        severity="HIGH",
        resolved_at=None,
        prevented=False,
    )

    print("event_id:", event.event_id)
    print("pre_snapshot length:", len(event.pre_snapshot))

    assert len(event.pre_snapshot) >= 10
    print("PASS")

    print("\n3. FIRST learn(event):")
    engine.learn(event)

    after_first = engine._patterns["dna_CRASH"].seen_count

    print("CRASH seen_count after first learn():", after_first)
    print("Increase:", after_first - initial_seen)

    assert after_first == initial_seen + 1
    print("PASS: new event learned exactly once.")

    print("\n4. SECOND learn(event):")
    engine.learn(event)

    after_second = engine._patterns["dna_CRASH"].seen_count

    print("CRASH seen_count after second learn():", after_second)
    print("Increase from initial:", after_second - initial_seen)

    assert after_second == after_first
    print("PASS: repeated learn() did not relearn the pattern.")

    print("\n5. VERIFY EVENT HISTORY:")
    matching = [
        e         for e in engine.get_failure_history(limit=500)
        if getattr(e, "event_id", None) == event.event_id
    ]

    print("Matching event occurrences:", len(matching))

    assert len(matching) == 1
    print("PASS")

    print("\n6. FINAL INVARIANTS:")
    print("NEW EVENT LEARNED:", after_first == initial_seen + 1)
    print("PATTERN NOT RELEARNED:", after_second == after_first)
    print("EVENT STORED ONCE:", len(matching) == 1)
    print("EVENT ID STABLE:", matching[0].event_id == event.event_id)

    assert after_first == initial_seen + 1
    assert after_second == after_first
    assert len(matching) == 1

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
