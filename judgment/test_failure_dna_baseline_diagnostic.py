from __future__ import annotations

import inspect
import json

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILURE-DNA BASELINE PERSISTENCE DIAGNOSTIC ===")

    engine = FailureDNAEngine()

    print("\n=== INITIAL BASELINE ===")
    print(json.dumps(engine._baseline_stats, indent=2, default=str))

    print("\n=== BASELINE-RELATED METHODS ===")

    methods = [
        name
        for name in dir(FailureDNAEngine)
        if "baseline" in name.lower()
        or "snapshot" in name.lower()
        or "metric" in name.lower()
    ]

    print(methods)

    for name in methods:
        attribute = getattr(FailureDNAEngine, name)

        if callable(attribute):
            try:
                print(f"\n--- {name} ---")
                print(inspect.signature(attribute))
                print(inspect.getsource(attribute))
            except (TypeError, OSError):
                pass

    print("\n=== CONSTRUCTOR SOURCE ===")
    print(inspect.getsource(FailureDNAEngine.__init__))

    print("\n=== TO-Z-SCORES SOURCE ===")
    print(inspect.getsource(FailureDNAEngine._to_z_scores))

    print("\n=== FILE-RELATED STATE ===")
    for name in [
        "_dna_file",
        "_history_file",
        "_baseline_stats",
        "_metric_buffer",
        "_patterns",
    ]:
        if hasattr(engine, name):
            value = getattr(engine, name)

            if name == "_metric_buffer":
                print(name, "length =", len(value))
            elif name == "_patterns":
                print(name, "keys =", list(value.keys()))
            else:
                print(name, "=", value)

    print("\n=== CURRENT PATTERNS ===")
    for pattern_id, pattern in engine._patterns.items():
        print(
            pattern_id,
            "| type=", pattern.failure_type,
            "| seen=", pattern.seen_count,
            "| confidence=", pattern.confidence,
        )


if __name__ == "__main__":
    main()
