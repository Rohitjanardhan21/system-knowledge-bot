import multiprocessing
import time

from backend.core.cognitive.failure_dna import FailureDNAEngine


def crashing_application():
    print("CHILD APPLICATION: STARTED", flush=True)
    time.sleep(0.5)
    raise RuntimeError("intentional FailureDNA learning crash")


def find_pattern(engine, pattern_id):
    for pattern in engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == pattern_id:
            return pattern
    return None


def main():
    print("=== REAL PROCESS CRASH -> FAILUREDNA LEARNING DIAGNOSTIC V2 ===")

    engine = FailureDNAEngine()

    print("\n1. INITIAL CRASH PATTERN:")

    crash = find_pattern(engine, "dna_CRASH")

    assert crash is not None

    initial_seen = crash.seen_count
    initial_history = engine.get_failure_history(limit=200)

    print("pattern_id:", crash.pattern_id)
    print("seen_count:", initial_seen)
    print("confidence:", crash.confidence)
    print("history size:", len(initial_history))

    print("PASS")

    print("\n2. STARTING REAL APPLICATION:")

    multiprocessing.freeze_support()

    process = multiprocessing.Process(
        target=crashing_application,
        name="FailureDNA-Learning-Crash-V2",
    )

    process.start()

    print("child PID:", process.pid)

    process.join(timeout=10)

    assert not process.is_alive()
    assert process.exitcode != 0

    print("child exitcode:", process.exitcode)
    print("PASS")

    print("\n3. RECORDING REAL PROCESS_CRASH:")

    description = (
        f"Real application process {process.pid} "
        "terminated unexpectedly during FailureDNA learning diagnostic"
    )

    before_record = engine.get_failure_history(limit=200)

    engine.record_failure(
        "PROCESS_CRASH",
        description,
        severity="HIGH",
    )

    after_record = engine.get_failure_history(limit=200)

    matching = [
        event
        for event in after_record
        if getattr(event, "event_type", None) == "PROCESS_CRASH"
        and str(process.pid) in getattr(event, "description", "")
    ]

    assert len(matching) == 1

    event = matching[0]

    print("event_id:", event.event_id)
    print("event_type:", event.event_type)
    print("pre_snapshot:", event.pre_snapshot)
    print("severity:", event.severity)

    print("History before:", len(before_record))
    print("History after:", len(after_record))

    print("PASS: exactly one crash event recorded.")

    print("\n4. CALLING learn():")

    returned = engine.learn(event)

    print("learn() returned:", returned)

    assert returned is event

    print("PASS: learn() accepted and returned the same FailureEvent.")

    print("\n5. CHECKING FOR DUPLICATE EVENTS:")

    history_after_learning = engine.get_failure_history(limit=200)

    same_event_id = [
        item
        for item in history_after_learning
        if getattr(item, "event_id", None) == event.event_id
    ]

    print(
        "Occurrences of event_id",
        event.event_id,
        ":",
        len(same_event_id),
    )

    assert len(same_event_id) == 1

    print("PASS: learning did not duplicate the event.")

    print("\n6. CHECKING CRASH PATTERN:")

    crash_after = find_pattern(engine, "dna_CRASH")

    assert crash_after is not None

    print("seen_count before:", initial_seen)
    print("seen_count after:", crash_after.seen_count)
    print("confidence before:", crash.confidence)
    print("confidence after:", crash_after.confidence)

    print("\n7. CHECKING SNAPSHOT REQUIREMENT:")

    print("PROCESS_CRASH pre_snapshot length:", len(event.pre_snapshot))

    if len(event.pre_snapshot) == 0:
        print(
            "OBSERVATION: this crash event contains no pre-crash "
            "telemetry snapshot, so it cannot provide a trajectory "
            "for signature learning."
        )
    else:
        print(
            "OBSERVATION: pre-crash telemetry exists and can potentially "
            "contribute to pattern learning."
        )

    print("\n8. FRESH ENGINE CHECK:")

    fresh_engine = FailureDNAEngine()

    fresh_crash = find_pattern(
        fresh_engine,
        "dna_CRASH",
    )

    assert fresh_crash is not None

    print(
        "fresh CRASH seen_count:",
        fresh_crash.seen_count,
    )

    print(
        "fresh CRASH confidence:",
        fresh_crash.confidence,
    )

    assert fresh_crash.seen_count == crash_after.seen_count

    print("PASS")

    print("\n9. FINAL INVARIANTS:")
    print("REAL APPLICATION CRASHED")
    print("PROCESS_CRASH RECORDED")
    print("PROCESS_CRASH HAS UNIQUE EVENT ID")
    print("learn() ACCEPTED EVENT")
    print("learn() DID NOT DUPLICATE EVENT")
    print("CRASH PATTERN REMAINS CONSISTENT")
    print("FRESH ENGINE LOAD VERIFIED")

    print("\nRESULT: PASS")


if __name__ == "__main__":
    main()
