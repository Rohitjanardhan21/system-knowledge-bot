from __future__ import annotations

import json
import uuid

from backend.core.cognitive.failure_dna import FailureDNAEngine


APP_NAME = "unstable_application.exe"
EVENT_TYPE = "PROCESS_CRASH"
MARKER = f"REPEATED_CRASH_ESCALATION_{uuid.uuid4().hex}"


def matching_events(engine):
    history = engine.get_failure_history(limit=500)

    return [
        event
        for event in history
        if getattr(event, "event_type", None) == EVENT_TYPE
        and MARKER in str(getattr(event, "description", ""))
    ]


def main():
    print("=== REPEATED CRASH FAILURE-DNA ESCALATION TEST ===")
    print(f"Marker: {MARKER}")

    engine = FailureDNAEngine()

    before = matching_events(engine)
    print(f"Matching events before: {len(before)}")

    assert len(before) == 0, "Unexpected marker collision"

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

        print(f"\n=== FAILURE-DNA EVENT {i} ===")
        print(f"record_failure() return value: {result}")

        current = matching_events(engine)

        print(f"Matching persisted events: {len(current)}")

        assert len(current) >= i, (
            f"Expected at least {i} persisted matching events, "
            f"found {len(current)}"
        )

        latest = current[0]

        print(f"Event ID: {getattr(latest, 'event_id', None)}")
        print(f"Event type: {getattr(latest, 'event_type', None)}")
        print(f"Severity: {getattr(latest, 'severity', None)}")
        print(f"Description: {getattr(latest, 'description', None)}")

        assert getattr(latest, "event_type", None) == EVENT_TYPE
        assert getattr(latest, "severity", None) == "HIGH"
        assert MARKER in str(getattr(latest, "description", ""))

    final_events = matching_events(engine)

    print("\n==============================================")
    print("FINAL MATCHING EVENTS:", len(final_events))

    for index, event in enumerate(final_events, 1):
        print(
            f"{index}. "
            f"id={getattr(event, 'event_id', None)} | "
            f"type={getattr(event, 'event_type', None)} | "
            f"severity={getattr(event, 'severity', None)}"
        )

    dna_summary = engine.get_dna_summary()
    health_score = engine.get_health_score()

    print("\n=== FAILURE-DNA STATE ===")
    print("DNA summary:")
    print(json.dumps(dna_summary, indent=2, default=str))

    print("Health score:")
    print(json.dumps(health_score, indent=2, default=str))

    assert len(final_events) >= 3
    assert all(
        getattr(event, "event_type", None) == EVENT_TYPE
        for event in final_events
    )

    print("\n==============================================")
    print("PASS: THREE REPEATED CRASH EVENTS WERE PERSISTED")
    print("==============================================")


if __name__ == "__main__":
    main()
