from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILUREDNA TRUST THRESHOLD REGRESSION V7 ===")

    engine = FailureDNAEngine()

    # ------------------------------------------------------------
    # 1. FIND CRASH PATTERN
    # ------------------------------------------------------------
    print("\n1. FINDING CRASH PATTERN:")

    crash = engine._patterns.get("dna_CRASH")

    assert crash is not None

    print("Initial seen_count:", crash.seen_count)
    print("Initial validated_predictions:", crash.validated_predictions)
    print("Initial correct_predictions:", crash.correct_predictions)
    print("Initial detection_accuracy:", crash.detection_accuracy)

    print("PASS")

    # ------------------------------------------------------------
    # 2. BELOW FULL TRUST THRESHOLD
    # ------------------------------------------------------------
    print("\n2. VERIFYING BELOW-THRESHOLD STATE:")

    crash.validated_predictions = 5
    crash.correct_predictions = 5
    crash.detection_accuracy = 1.0

    print("seen_count:", crash.seen_count)
    print("validated_predictions:", crash.validated_predictions)
    print("detection_accuracy:", crash.detection_accuracy)

    trust_before_seen_threshold = (
        engine.is_prediction_trustworthy("dna_CRASH")
    )

    print(
        "trustworthy:",
        trust_before_seen_threshold,
    )

    assert crash.seen_count < 15
    assert trust_before_seen_threshold is False

    print("PASS")

    # ------------------------------------------------------------
    # 3. REACH FULL TRUST THRESHOLD
    # ------------------------------------------------------------
    print("\n3. REACHING FULL TRUST THRESHOLD:")

    crash.seen_count = 15

    print("seen_count:", crash.seen_count)
    print("validated_predictions:", crash.validated_predictions)
    print("correct_predictions:", crash.correct_predictions)
    print("detection_accuracy:", crash.detection_accuracy)

    trust_after_threshold = (
        engine.is_prediction_trustworthy("dna_CRASH")
    )

    print(
        "trustworthy:",
        trust_after_threshold,
    )

    assert crash.seen_count >= 15
    assert crash.validated_predictions >= 5
    assert crash.detection_accuracy >= 0.70
    assert trust_after_threshold is True

    print("PASS")

    # ------------------------------------------------------------
    # 4. VERIFY SUMMARY REPRESENTATION
    # ------------------------------------------------------------
    print("\n4. VERIFYING DNA SUMMARY REPRESENTATION:")

    summary = engine.get_dna_summary()

    crash_summary = None

    for pattern in summary.get("pattern_list", []):
        if pattern.get("type") == "CRASH":
            crash_summary = pattern
            break

    assert crash_summary is not None

    print("CRASH summary:", crash_summary)

    # Internal accuracy is a ratio: 1.0
    assert crash.detection_accuracy == 1.0

    # Public summary represents accuracy as a percentage: 100.0
    assert crash_summary["accuracy"] == 100.0

    assert crash_summary["trustworthy"] is True

    print("Internal accuracy ratio:", crash.detection_accuracy)
    print("Summary accuracy percentage:", crash_summary["accuracy"])
    print("Summary trustworthy:", crash_summary["trustworthy"])

    print("PASS")

    # ------------------------------------------------------------
    # 5. VERIFY OTHER SUMMARY FIELDS
    # ------------------------------------------------------------
    print("\n5. VERIFYING SUMMARY CONSISTENCY:")

    assert crash_summary["seen"] == crash.seen_count
    assert crash_summary["confidence"] == crash.confidence * 100
    assert crash_summary["prevented"] == crash.prevented_count

    print("seen:", crash_summary["seen"])
    print("prevented:", crash_summary["prevented"])
    print("confidence:", crash_summary["confidence"])
    print("accuracy:", crash_summary["accuracy"])
    print("trustworthy:", crash_summary["trustworthy"])

    print("PASS")

    # ------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------
    print("\n=== RESULT ===")
    print("FAILUREDNA TRUST THRESHOLD REGRESSION: PASS")
    print("Trustworthiness requires:")
    print("  seen_count >= 15")
    print("  validated_predictions >= 5")
    print("  detection_accuracy >= 0.70")
    print("Summary correctly exposes accuracy as a percentage.")
    print("Summary correctly exposes trustworthy=True.")


if __name__ == "__main__":
    main()
