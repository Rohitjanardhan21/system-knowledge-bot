from __future__ import annotations

import inspect
import json

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILURE-DNA REPEATED-CRASH LEARNING DIAGNOSTIC ===")

    engine = FailureDNAEngine()

    print("\n=== CURRENT CRASH PATTERN ===")

    summary = engine.get_dna_summary()

    crash_patterns = [
        pattern
        for pattern in summary.get("pattern_list", [])
        if str(pattern.get("type", "")).upper() in {"CRASH", "PROCESS_CRASH"}
    ]

    print(json.dumps(crash_patterns, indent=2, default=str))

    print("\n=== FAILURE HISTORY ===")

    history = engine.get_failure_history(limit=20)

    for index, event in enumerate(history, 1):
        print(
            f"{index}. "
            f"id={getattr(event, 'event_id', None)} | "
            f"type={getattr(event, 'event_type', None)} | "
            f"severity={getattr(event, 'severity', None)} | "
            f"description={getattr(event, 'description', None)}"
        )

    print("\n=== PREDICT METHOD SIGNATURE ===")
    print(inspect.signature(engine.predict))

    print("\n=== LEARN METHOD SIGNATURE ===")
    print(inspect.signature(engine.learn))

    print("\n=== PREDICT SOURCE ===")
    print(inspect.getsource(FailureDNAEngine.predict))

    print("\n=== LEARN SOURCE ===")
    print(inspect.getsource(FailureDNAEngine.learn))


if __name__ == "__main__":
    main()
