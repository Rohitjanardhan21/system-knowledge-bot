import inspect

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILUREDNA INTERNAL TRUST RULE DIAGNOSTIC ===")

    engine = FailureDNAEngine()

    print("\n1. _is_pattern_trustworthy() SOURCE:")

    assert hasattr(
        engine,
        "_is_pattern_trustworthy",
    ), "_is_pattern_trustworthy() not found"

    source = inspect.getsource(
        engine._is_pattern_trustworthy
    )

    print(source)

    print("\n2. CURRENT CRASH PATTERN:")

    crash = engine._patterns.get("dna_CRASH")

    assert crash is not None

    print("pattern_id:", crash.pattern_id)
    print("seen_count:", crash.seen_count)
    print("confidence:", crash.confidence)
    print("validated_predictions:", crash.validated_predictions)
    print("correct_predictions:", crash.correct_predictions)
    print("detection_accuracy:", crash.detection_accuracy)

    print("\n3. DIRECT INTERNAL TRUST RESULT:")

    result = engine._is_pattern_trustworthy(crash)

    print("_is_pattern_trustworthy:", result)

    print("\n4. CLASS / MODULE CONSTANTS:")

    module = inspect.getmodule(engine)

    if module is not None:
        for name in sorted(dir(module)):
            upper = name.upper()

            if any(
                keyword in upper
                for keyword in (
                    "TRUST",
                    "ACCURACY",
                    "VALID",
                    "MIN_",
                    "THRESHOLD",
                    "SAMPLE",
                )
            ):
                value = getattr(module, name)

                if not callable(value):
                    print(
                        name,
                        "=",
                        repr(value),
                    )

    print("\nRESULT: DIAGNOSTIC COMPLETE.")


if __name__ == "__main__":
    main()
