from __future__ import annotations

import inspect
import json

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILURE-DNA CRASH MATCHING DIAGNOSTIC ===")

    engine = FailureDNAEngine()

    print("\n=== MATCH-PATTERN SIGNATURE ===")
    print(inspect.signature(engine._match_pattern))

    print("\n=== MATCH-PATTERN SOURCE ===")
    print(inspect.getsource(FailureDNAEngine._match_pattern))

    print("\n=== SNAPSHOT EXTRACTION SOURCE ===")
    print(inspect.getsource(FailureDNAEngine._extract_snapshot))

    print("\n=== PATTERN LEARNING SOURCE ===")
    print(inspect.getsource(FailureDNAEngine._learn_pattern))

    print("\n=== CRASH PATTERN FROM CURRENT STATE ===")

    summary = engine.get_dna_summary()

    crash_patterns = [
        p for p in summary.get("pattern_list", [])
        if str(p.get("type", "")).upper() == "CRASH"
    ]

    print(json.dumps(crash_patterns, indent=2, default=str))

    print("\n=== INTERNAL CRASH PATTERNS ===")

    for pattern_id, pattern in engine._patterns.items():
        if str(pattern.failure_type).upper() == "CRASH":
            print("Pattern ID:", pattern_id)
            print("Failure type:", pattern.failure_type)
            print("Seen count:", pattern.seen_count)
            print("Confidence:", pattern.confidence)
            print("Signature steps:", pattern.signature_steps)
            print("Signature timing:", pattern.signature_timing)
            print("Lead time:", pattern.avg_lead_time_minutes)
            print("Plain description:", pattern.plain_description)


if __name__ == "__main__":
    main()
