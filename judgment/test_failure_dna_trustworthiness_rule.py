import inspect

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILUREDNA TRUSTWORTHINESS RULE DIAGNOSTIC ===")

    engine = FailureDNAEngine()

    print("\n1. is_prediction_trustworthy() SOURCE:")

    source = inspect.getsource(
        engine.is_prediction_trustworthy
    )

    print(source)

    print("\n2. CURRENT CRASH PATTERN:")

    crash = None

    for pattern in engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == "dna_CRASH":
            crash = pattern
            break

    assert crash is not None

    print("pattern_id:", crash.pattern_id)
    print("validated_predictions:", crash.validated_predictions)
    print("correct_predictions:", crash.correct_predictions)
    print("detection_accuracy:", crash.detection_accuracy)
    print("confidence:", crash.confidence)
    print("seen_count:", crash.seen_count)

    print("\n3. CURRENT TRUSTWORTHINESS RESULT:")

    result = engine.is_prediction_trustworthy(
        "dna_CRASH"
    )

    print("trustworthy:", result)

    print("\n4. RELATED ENGINE CONSTANTS:")

    for name in sorted(dir(engine)):
        upper = name.upper()

        if any(
            keyword in upper
            for keyword in (
                "TRUST",
                "ACCURACY",
                "VALID",
                "MIN_",
                "THRESHOLD",
            )
        ):
            value = getattr(engine, name)

            if not callable(value):
                print(
                    name,
                    "=",
                    repr(value),
                )

    print("\nRESULT: DIAGNOSTIC COMPLETE.")


if __name__ == "__main__":
    main()
