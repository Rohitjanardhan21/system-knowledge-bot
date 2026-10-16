import time

from backend.core.cognitive.failure_dna import (
    FailureDNAEngine,
    ActivePrediction,
)


def main():
    print("=== FAILUREDNA PREDICTION RESOLUTION IDEMPOTENCY REGRESSION V1 ===")

    engine = FailureDNAEngine()

    # ------------------------------------------------------------
    # REAL-LIFE SCENARIO
    # ------------------------------------------------------------
    print("\nREAL-LIFE SCENARIO:")
    print("FailureDNA predicts an application crash.")
    print("The application actually crashes.")
    print("The same crash outcome is accidentally delivered twice")
    print("because of a retry/recovery/concurrent-processing race.")
    print("The prediction must only be validated ONCE.")

    # ------------------------------------------------------------
    # 1. FIND CRASH PATTERN
    # ------------------------------------------------------------
    print("\n1. FINDING CRASH PATTERN:")

    crash = engine._patterns.get("dna_CRASH")

    assert crash is not None

    print("Initial validated_predictions:",
          crash.validated_predictions)

    print("Initial correct_predictions:",
          crash.correct_predictions)

    print("Initial detection_accuracy:",
          crash.detection_accuracy)

    initial_validated = crash.validated_predictions
    initial_correct = crash.correct_predictions

    print("PASS")

    # ------------------------------------------------------------
    # 2. CREATE PREDICTION
    # ------------------------------------------------------------
    print("\n2. CREATING ACTIVE CRASH PREDICTION:")

    prediction_id = (
        f"pred_resolution_idempotency_v1_{time.time_ns()}"
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
    print("resolved:", prediction.resolved)
    print("was_correct:", prediction.was_correct)

    assert prediction.resolved is False
    assert prediction.was_correct is None

    print("PASS")

    # ------------------------------------------------------------
    # 3. FIRST RESOLUTION
    # ------------------------------------------------------------
    print("\n3. FIRST RESOLUTION — REAL CRASH OUTCOME:")

    first_result = engine.resolve_prediction(
        prediction_id,
        True,
    )

    print("first result:", first_result)
    print("resolved:", first_result.resolved)
    print("was_correct:", first_result.was_correct)

    assert first_result.resolved is True
    assert first_result.was_correct is True

    print(
        "validated_predictions:",
        crash.validated_predictions,
    )

    print(
        "correct_predictions:",
        crash.correct_predictions,
    )

    assert (
        crash.validated_predictions
        == initial_validated + 1
    )

    assert (
        crash.correct_predictions
        == initial_correct + 1
    )

    print("PASS")

    # ------------------------------------------------------------
    # 4. DUPLICATE RESOLUTION
    # ------------------------------------------------------------
    print("\n4. DUPLICATE RESOLUTION — SAME OUTCOME ARRIVES AGAIN:")

    second_result = engine.resolve_prediction(
        prediction_id,
        True,
    )

    print("second result:", second_result)

    print(
        "validated_predictions:",
        crash.validated_predictions,
    )

    print(
        "correct_predictions:",
        crash.correct_predictions,
    )

    # ------------------------------------------------------------
    # 5. IDEMPOTENCY ASSERTION
    # ------------------------------------------------------------
    print("\n5. VERIFYING NO DOUBLE COUNT:")

    expected_validated = initial_validated + 1
    expected_correct = initial_correct + 1

    print(
        "expected validated_predictions:",
        expected_validated,
    )

    print(
        "actual validated_predictions:",
        crash.validated_predictions,
    )

    print(
        "expected correct_predictions:",
        expected_correct,
    )

    print(
        "actual correct_predictions:",
        crash.correct_predictions,
    )

    assert (
        crash.validated_predictions
        == expected_validated
    )

    assert (
        crash.correct_predictions
        == expected_correct
    )

    print("No double-counting: PASS")

    # ------------------------------------------------------------
    # 6. VERIFY PREDICTION REMAINS TERMINAL
    # ------------------------------------------------------------
    print("\n6. VERIFYING TERMINAL PREDICTION STATE:")

    stored_prediction = engine._active_predictions.get(
        prediction_id
    )

    assert stored_prediction is not None

    print("resolved:", stored_prediction.resolved)
    print("was_correct:", stored_prediction.was_correct)

    assert stored_prediction.resolved is True
    assert stored_prediction.was_correct is True

    print("Terminal state preserved: PASS")

    # ------------------------------------------------------------
    # 7. VERIFY ACCURACY
    # ------------------------------------------------------------
    print("\n7. VERIFYING ACCURACY WAS NOT ARTIFICIALLY INFLATED:")

    expected_accuracy = (
        crash.correct_predictions
        / crash.validated_predictions
    )

    print("expected accuracy:", expected_accuracy)
    print("actual accuracy:", crash.detection_accuracy)

    assert abs(
        crash.detection_accuracy
        - expected_accuracy
    ) < 1e-9

    print("Accuracy integrity: PASS")

    # ------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------
    print("\n=== RESULT ===")
    print("PREDICTION RESOLUTION IDEMPOTENCY: PASS")
    print(
        "The same prediction outcome cannot be counted twice."
    )


if __name__ == "__main__":
    main()
