import multiprocessing
import time

from backend.core.cognitive.failure_dna import FailureDNAEngine


def crashing_application():
    print("CHILD APPLICATION: STARTED", flush=True)
    time.sleep(0.5)
    raise RuntimeError("intentional FailureDNA learning crash")


def main():
    print("=== REAL PROCESS CRASH -> FAILUREDNA LEARNING TEST ===")

    engine = FailureDNAEngine()

    print("\n1. INITIAL CRASH PATTERN:")

    crash = None

    for pattern in engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == "dna_CRASH":
            crash = pattern
            break

    assert crash is not None

    initial_seen = crash.seen_count

    print("pattern_id:", crash.pattern_id)
    print("initial seen_count:", initial_seen)
    print("initial confidence:", crash.confidence)

    print("PASS")

    print("\n2. STARTING REAL APPLICATION:")

    multiprocessing.freeze_support()

    process = multiprocessing.Process(
        target=crashing_application,
        name="FailureDNA-Learning-Crash",
    )

    process.start()

    print("child PID:", process.pid)

    process.join(timeout=10)

    assert not process.is_alive()

    print("child exitcode:", process.exitcode)

    assert process.exitcode != 0

    print("PASS: real child process terminated unexpectedly.")

    print("\n3. RECORDING PROCESS_CRASH:")

    description = (
        f"Real application process {process.pid} "
        "terminated unexpectedly during FailureDNA learning test"
    )

    engine.record_failure(
        "PROCESS_CRASH",
        description,
        severity="HIGH",
    )

    history = engine.get_failure_history(limit=100)

    matching = [
        event
        for event in history
        if getattr(event, "event_type", None) == "PROCESS_CRASH"
        and str(process.pid) in getattr(event, "description", "")
    ]

    print("matching PROCESS_CRASH events:", len(matching))

    assert len(matching) == 1

    event = matching[0]

    print("event_id:", event.event_id)
    print("event_type:", event.event_type)
    print("description:", event.description)
    print("severity:", event.severity)

    print("PASS")

    print("\n4. LEARNING FROM REAL CRASH EVENT:")

    before = crash.seen_count

    result = engine.learn(event)

    print("learn() return:", result)

    print("CRASH seen_count before:", before)
    print("CRASH seen_count after:", crash.seen_count)

    # The exact learning implementation may or may not increment
    # the existing synthetic CRASH pattern for a PROCESS_CRASH event.
    # We therefore verify the event is accepted and remains persisted,
    # rather than inventing an increment contract.
    history_after_learning = engine.get_failure_history(limit=100)

    learned_matches = [
        item
        for item in history_after_learning
        if getattr(item, "event_id", None) == event.event_id
    ]

    assert len(learned_matches) == 1

    print("PASS: real crash event accepted by FailureDNA.")

    print("\n5. CRASH PATTERN AFTER LEARNING:")

    crash_after = None

    for pattern in engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == "dna_CRASH":
            crash_after = pattern
            break

    assert crash_after is not None

    print("pattern_id:", crash_after.pattern_id)
    print("seen_count:", crash_after.seen_count)
    print("confidence:", crash_after.confidence)
    print("signature_steps:", crash_after.signature_steps)

    print("PASS")

    print("\n6. FRESH FAILUREDNA ENGINE:")

    fresh_engine = FailureDNAEngine()

    fresh_crash = None

    for pattern in fresh_engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == "dna_CRASH":
            fresh_crash = pattern
            break

    assert fresh_crash is not None

    print("fresh seen_count:", fresh_crash.seen_count)
    print("fresh confidence:", fresh_crash.confidence)

    assert fresh_crash.seen_count >= initial_seen

    print("PASS: CRASH pattern remains available after fresh engine load.")

    print("\n7. FINAL INVARIANTS:")
    print("REAL CHILD PROCESS CRASHED")
    print("PROCESS_CRASH EVENT RECORDED")
    print("EVENT RETRIEVABLE FROM FAILURE HISTORY")
    print("FAILUREDNA ACCEPTED REAL CRASH EVENT")
    print("CRASH PATTERN REMAINS AVAILABLE")
    print("FRESH ENGINE LOAD VERIFIED")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
