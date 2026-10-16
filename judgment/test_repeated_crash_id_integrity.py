from __future__ import annotations

import json
import uuid

from backend.core.cognitive.failure_dna import FailureDNAEngine


APP_NAME = "unstable_application.exe"
EVENT_TYPE = "PROCESS_CRASH"
MARKER = f"REPEATED_CRASH_IDENTITY_{uuid.uuid4().hex}"


def matching_events(engine):
    history = engine.get_failure_history(limit=500)

    return [
        event
        for event in history
        if getattr(event, "event_type", None) == EVENT_TYPE
        and MARKER in str(getattr(event, "description", ""))
    ]


def main():
    print("=== REPEATED CRASH IDENTITY + HEALTH TEST ===")
    print(f"Marker: {MARKER}")

    engine = FailureDNAEngine()

    before = matching_events(engine)
    assert len(before) == 0

    for i in range(1, 4):
        description = (
            f"{MARKER}: Application {APP_NAME} crashed "
            f"during repeated-crash test #{i}"
        )

        result = engine.record_failure(
            EVENT_TYPE,
            description,
            severity="HIGH",
        )

        print(f"\n=== FAILURE {i} ===")
        print(f"record_failure() return: {result}")

        current = matching_events(engine)

        assert len(current) >= i, (
            f"Expected at least {i} matching events, "
            f"found {len(current)}"
        )

        latest = current[0]

        print(f"Event ID: {getattr(latest, 'event_id', None)}")
        print(f"Event type: {getattr(latest, 'event_type', None)}")
        print(f"Severity: {getattr(latest, 'severity', None)}")
        print(f"Description: {getattr(latest, 'description', None)}")

    events = matching_events(engine)

    print("\n==============================================")
    print("PERSISTED EVENTS:", len(events))

    event_ids = [
        getattr(event, "event_id", None)
        for event in events
    ]

    print("EVENT IDS:")
    for event_id in event_ids:
        print(f"  {event_id}")

    print("\nUNIQUE EVENT IDS:", len(set(event_ids)))
    print("TOTAL EVENT IDS:", len(event_ids))

    assert len(events) >= 3

    # This is an important integrity assertion.
    assert all(event_ids), "Every failure event must have an event_id"

    assert len(set(event_ids)) == len(event_ids), (
        "FAILURE-ID COLLISION: distinct crash events share event_id(s)"
    )

    dna_summary = engine.get_dna_summary()

    metrics = {
        "cpu": 25.0,
        "memory": 40.0,
        "disk": 35.0,
        "temperature": 45.0,
        "anomaly_score": 0.1,
    }

    health_score = engine.get_health_score(metrics)

    print("\n=== DNA SUMMARY ===")
    print(json.dumps(dna_summary, indent=2, default=str))

    print("\n=== HEALTH SCORE ===")
    print(json.dumps(health_score, indent=2, default=str))

    print("\n==============================================")
    print("PASS: REPEATED CRASH EVENTS HAVE DISTINCT IDS")
    print("FAILURE-DNA HEALTH CALCULATION ACCEPTED METRICS")
    print("==============================================")


if __name__ == "__main__":
    main()
