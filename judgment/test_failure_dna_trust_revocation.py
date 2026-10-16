from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILUREDNA TRUST REVOCATION REGRESSION V1 ===")

    engine = FailureDNAEngine()

    # ------------------------------------------------------------
    # REAL-LIFE SCENARIO
    # ------------------------------------------------------------
    print("\nREAL-LIFE SCENARIO:")
    print("A CRASH pattern was previously trusted.")
    print("A software/workload change makes the pattern unreliable.")
    print("New false predictions reduce its historical accuracy.")
    print("The system must revoke trust when accuracy falls below 70%.")

    # ------------------------------------------------------------
    # 1. FIND CRASH PATTERN
    # ------------------------------------------------------------
    print("\n1. FINDING CRASH PATTERN:")

    crash = engine._patterns.get("dna_CRASH")

    assert crash is not None

    print("Initial seen_count:", crash.seen_count)
    print(
        "Initial validated_predictions:",
        crash.validated_predictions,
    )
    print(
        "Initial correct_predictions:",
        crash.correct_predictions,
    )
    print(
        "Initial detection_accuracy:",
        crash.detection_accuracy,
    )

    print("PASS")

    # ------------------------------------------------------------
    # 2. ESTABLISH A TRUSTED PATTERN
    # ------------------------------------------------------------
    print("\n2. ESTABLISHING TRUSTED BASELINE:")

    crash.seen_count = 15
    crash.validated_predictions = 5
    crash.correct_predictions = 5
    crash.detection_accuracy = 1.0

    trusted_before = engine.is_prediction_trustworthy(
        "dna_CRASH"
    )

    print("seen_count:", crash.seen_count)
    print(
        "validated_predictions:",
        crash.validated_predictions,
    )
    print(
        "correct_predictions:",
        crash.correct_predictions,
    )
    print(
        "detection_accuracy:",
        crash.detection_accuracy,
    )
    print("trustworthy:", trusted_before)

    assert trusted_before is True

    print("PASS")

    # ------------------------------------------------------------
    # 3. SIMULATE NEW FALSE PREDICTIONS
    # ------------------------------------------------------------
    print("\n3. SIMULATING NEW FALSE PREDICTIONS:")

    # Five additional validated predictions occur.
    #
    # Only ONE of the five is correct.
    #
    # Final state:
    #   validated = 10
    #   correct   = 6
    #   accuracy  = 60%
    #
    # This represents a previously reliable pattern becoming
    # unreliable after a software/workload change.

    crash.validated_predictions += 5
    crash.correct_predictions += 1

    crash.detection_accuracy = (
        crash.correct_predictions
        / crash.validated_predictions
    )

    print(
        "validated_predictions:",
        crash.validated_predictions,
    )
    print(
        "correct_predictions:",
        crash.correct_predictions,
    )
    print(
        "detection_accuracy:",
        crash.detection_accuracy,
    )

    assert crash.validated_predictions == 10
    assert crash.correct_predictions == 6
    assert abs(
        crash.detection_accuracy - 0.60
    ) < 1e-9

    print("PASS")

    # ------------------------------------------------------------
    # 4. VERIFY TRUST REVOCATION
    # ------------------------------------------------------------
    print("\n4. VERIFYING TRUST REVOCATION:")

    trusted_after = engine.is_prediction_trustworthy(
        "dna_CRASH"
    )

    print(
        "trustworthy after accuracy degradation:",
        trusted_after,
    )

    assert trusted_after is False

    print("PASS")

    # ------------------------------------------------------------
    # 5. VERIFY SUMMARY
    # ------------------------------------------------------------
    print("\n5. VERIFYING DNA SUMMARY:")

    summary = engine.get_dna_summary()

    crash_summary = None

    for pattern in summary.get("pattern_list", []):
        if pattern.get("type") == "CRASH":
            crash_summary = pattern
            break

    assert crash_summary is not None

    print("CRASH summary:", crash_summary)

    assert crash_summary["accuracy"] == 60.0
    assert crash_summary["trustworthy"] is False

    print("Summary accuracy: PASS")
    print("Summary trustworthiness: PASS")

    # ------------------------------------------------------------
    # 6. VERIFY SAFETY IMPLICATION
    # ------------------------------------------------------------
    print("\n6. SAFETY CONTRACT:")

    print(
        "Pattern had previously earned trust:",
        trusted_before,
    )

    print(
        "Pattern lost trust after accuracy fell:",
        not trusted_after,
    )

    assert trusted_before is True
    assert trusted_after is False

    print("Dynamic trust revocation: PASS")

    # ------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------
    print("\n=== RESULT ===")
    print("FAILUREDNA TRUST REVOCATION: PASS")
    print(
        "A previously trusted pattern can lose trust "
        "when prediction accuracy deteriorates."
    )


if __name__ == "__main__":
    main()
