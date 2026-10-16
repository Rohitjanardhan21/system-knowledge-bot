import time

from backend.core.cognitive.failure_dna import (
    FailureDNAEngine,
    ActivePrediction,
)


def main():
    print("=== FAILUREDNA FALSE-POSITIVE VALIDATION REGRESSION V1 ===")

    engine = FailureDNAEngine()

    # ------------------------------------------------------------
    # REAL-LIFE SCENARIO
    # ------------------------------------------------------------
    print("\nREAL-LIFE SCENARIO:")
    print("FailureDNA predicts an application crash.")
    print("The application does NOT crash.")
    print("This is a FALSE POSITIVE.")
    print("The prediction must count as validated, but NOT correct.")

    # ------------------------------------------------------------
    # 1. FIND CRASH PATTERN
    # ------------------------------------------------------------
    print("\n1. FINDING CRASH PATTERN:")

    crash = engine._patterns.get("dna_CRASH")

    assert crash is not None, "CRASH pattern not found"

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

    initial_validated = crash.validated_predictions
    initial_correct = crash.correct_predictions

    print("PASS")

    # ------------------------------------------------------------
    # 2. CREATE FALSE-POSITIVE PREDICTION
    # ------------------------------------------------------------
    print("\n2. CREATING ACTIVE CRASH PREDICTION:")

    prediction_id = (
        f"pred_false_positive_v1_{time.time_ns()}"
    )

    prediction = ActivePrediction(
        prediction_id=prediction_id,
        failure_type="CRASH",
        detected_at=time.time(),
        predicted_eta=time.time() + 300,
        confidence=0.91,
        minutes_remaining=5.0,
        plain_message="Synthetic crash prediction",
        plain_action=(
            "Save your work and restart the affected application"
        ),
        severity="HIGH",
        pattern_id="dna_CRASH",
    )

    engine._active_predictions[prediction_id] = prediction

    print("prediction_id:", prediction_id)
    print("failure_type:", prediction.failure_type)
    print("confidence:", prediction.confidence)
    print("resolved:", prediction.resolved)
    print("was_correct:", prediction.was_correct)

    assert prediction.resolved is False
    assert prediction.was_correct is None

    print("PASS")

    # ------------------------------------------------------------
    # 3. REALITY: APPLICATION DID NOT CRASH
    # ------------------------------------------------------------
    print("\n3. SIMULATING REAL-WORLD OUTCOME:")

    print("Predicted event: CRASH")
    print("Actual event:   NO CRASH")
    print("Outcome:        FALSE POSITIVE")

    print("PASS")

    # ------------------------------------------------------------
    # 4. RESOLVE AS FALSE
    # ------------------------------------------------------------
    print("\n4. RESOLVING PREDICTION AS FALSE POSITIVE:")

    result = engine.resolve_prediction(
        prediction_id,
        False,
    )

    print("resolve_prediction() returned:", result)

    assert result is not None

    print("PASS")

    # ------------------------------------------------------------
    # 5. VERIFY PREDICTION STATE
    # ------------------------------------------------------------
    print("\n5. VERIFYING PREDICTION STATE:")

    resolved_prediction = engine._active_predictions.get(
        prediction_id
    )

    assert resolved_prediction is not None

    print(
        "resolved:",
        resolved_prediction.resolved,
    )

    print(
        "was_correct:",
        resolved_prediction.was_correct,
    )

    assert resolved_prediction.resolved is True
    assert resolved_prediction.was_correct is False

    print("PASS")

    # ------------------------------------------------------------
    # 6. VERIFY VALIDATION COUNTERS
    # ------------------------------------------------------------
    print("\n6. VERIFYING VALIDATION COUNTERS:")

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

    # Every resolved prediction is a validated outcome.
    assert (
        crash.validated_predictions
        == initial_validated + 1
    )

    # A false positive must NOT count as correct.
    assert (
        crash.correct_predictions
        == initial_correct
    )

    print("validated_predictions increased: PASS")
    print("correct_predictions unchanged: PASS")

    # ------------------------------------------------------------
    # 7. VERIFY ACCURACY
    # ------------------------------------------------------------
    print("\n7. VERIFYING ACCURACY DEGRADATION:")

    expected_accuracy = (
        crash.correct_predictions
        / crash.validated_predictions
    )

    print(
        "expected_accuracy:",
        expected_accuracy,
    )

    print(
        "actual_accuracy:",
        crash.detection_accuracy,
    )

    assert abs(
        crash.detection_accuracy
        - expected_accuracy
    ) < 1e-9

    print("Accuracy correctly reflects false positive: PASS")

    # ------------------------------------------------------------
    # 8. VERIFY TRUST IMPACT
    # ------------------------------------------------------------
    print("\n8. VERIFYING TRUST IMPACT:")

    trustworthy = engine.is_prediction_trustworthy(
        "dna_CRASH"
    )

    print(
        "CRASH pattern trustworthy:",
        trustworthy,
    )

    # With a sufficiently mature pattern, the false positive
    # must be reflected in the trust decision according to
    # the centralized >=70% accuracy rule.
    if crash.validated_predictions >= 5:
        expected_trust = (
            crash.seen_count >= 15
            and crash.detection_accuracy >= 0.70
        )

        print(
            "Expected trust from current state:",
            expected_trust,
        )

        assert trustworthy is expected_trust

    print("PASS")

    # ------------------------------------------------------------
    # 9. VERIFY SUMMARY
    # ------------------------------------------------------------
    print("\n9. VERIFYING DNA SUMMARY:")

    summary = engine.get_dna_summary()

    crash_summary = None

    for pattern in summary.get("pattern_list", []):
        if pattern.get("type") == "CRASH":
            crash_summary = pattern
            break

    assert crash_summary is not None

    print("CRASH summary:", crash_summary)

    assert crash_summary["accuracy"] is not None

    expected_summary_accuracy = (
        crash.detection_accuracy * 100
    )

    assert abs(
        crash_summary["accuracy"]
        - expected_summary_accuracy
    ) < 1e-9

    assert (
        crash_summary["trustworthy"]
        == trustworthy
    )

    print("Summary accuracy: PASS")
    print("Summary trustworthiness: PASS")

    # ------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------
    print("\n=== RESULT ===")
    print("FALSE-POSITIVE VALIDATION REGRESSION: PASS")
    print(
        "A false prediction is counted as validated,"
        " not correct."
    )
    print(
        "Prediction accuracy reflects the false positive."
    )
    print(
        "Trustworthiness reflects the degraded accuracy."
    )


if __name__ == "__main__":
    main()
