from __future__ import annotations

import inspect
import uuid

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILURE EVENT ID GENERATION DIAGNOSTIC ===")

    source = inspect.getsource(FailureDNAEngine.record_failure)

    print("\n=== record_failure() SOURCE ===")
    print(source)

    engine = FailureDNAEngine()

    marker = f"ID_DIAGNOSTIC_{uuid.uuid4().hex}"

    print("\n=== GENERATING TWO DISTINCT EVENTS ===")

    engine.record_failure(
        "PROCESS_CRASH",
        f"{marker}: crash A",
        severity="HIGH",
    )

    engine.record_failure(
        "PROCESS_CRASH",
        f"{marker}: crash B",
        severity="HIGH",
    )

    events = [
        event
        for event in engine.get_failure_history(limit=500)
        if marker in str(getattr(event, "description", ""))
    ]

    print(f"\nEvents found: {len(events)}")

    for index, event in enumerate(events, 1):
        print(
            f"{index}. "
            f"id={getattr(event, 'event_id', None)} | "
            f"type={getattr(event, 'event_type', None)} | "
            f"description={getattr(event, 'description', None)}"
        )

    ids = [
        getattr(event, "event_id", None)
        for event in events
    ]

    print("\nIDs:", ids)
    print("Unique IDs:", len(set(ids)))

    if len(events) >= 2 and len(set(ids)) < len(ids):
        print("\nRESULT: CONFIRMED ID COLLISION")
        print("Distinct failure events are sharing an event_id.")
    else:
        print("\nRESULT: NO COLLISION OBSERVED")


if __name__ == "__main__":
    main()
