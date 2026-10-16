import time

from backend.core.cognitive.failure_dna import (
    FailureDNAEngine,
    ActivePrediction,
)


def main():
    print("=== FAILUREDNA PREDICTION EXPIRY REGRESSION V1 ===")

    engine = FailureDNAEngine()

    # ------------------------------------------------------------
    # REAL-LIFE SCENARIO
    # ------------------------------------------------------------
    print("\nREAL-LIFE SCENARIO:")
    print("FailureDNA predicts an application crash.")
    print("The prediction window expires.")
    print("No crash is observed during that window.")
    print("Expiry must NOT be treated as a validated prediction outcome.")

    # ------------------------------------------------------------
    # 1. FIND CRASH PATTERN
    # ------------------------------------------------------------
    print("\n1. FINDING CRASH PATTERN:")

    crash = engine._patterns.get("dna_CRASH")

    assert crash is not None

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
    initial_accuracy = crash.detection_accuracy

    print("PASS")

    # ------------------------------------------------------------
    # 2. CREATE ALREADY-EXPIRED PREDICTION
    # ------------------------------------------------------------
    print("\n2. CREATING EXPIRED PREDICTION:")

    prediction_id = (
        f"pred_expiry_v1_{time.time_ns()}"
    )

    prediction = ActivePrediction(
        prediction_id=prediction_id,
        failure_type="CRASH",
        detected_at=time.time() - 600,
        predicted_eta=time.time() - 60,
        confidence=0.91,
        minutes_remaining=0.0,
        plain_message="Expired synthetic crash prediction",
        plain_action=(
            "Save your work and restart the affected application"
        ),
        severity="HIGH",
        pattern_id="dna_CRASH",
    )

    engine._active_predictions[prediction_id] = prediction

    print("prediction_id:", prediction_id)
    print("detected_at:", prediction.detected_at)
    print("predicted_eta:", prediction.predicted_eta)
    print("current_time:", time.time())
    print("resolved:", prediction.resolved)
    print("was_correct:", prediction.was_correct)

    assert prediction.resolved is False
    assert prediction.was_correct is None
    assert prediction.predicted_eta < time.time()

    print("PASS")

    # ------------------------------------------------------------
    # 3. VERIFY IT IS INITIALLY ACTIVE
    # ------------------------------------------------------------
    print("\n3. VERIFYING INITIAL ACTIVE STATE:")

    active_before = [
        p for p in engine.get_active_predictions()
        if p.prediction_id == prediction_id
    ]

    print(
        "prediction present in active list:",
        len(active_before) == 1,
    )

    assert len(active_before) == 1

    print("PASS")

    # ------------------------------------------------------------
    # 4. TRIGGER PREDICTION LIFECYCLE
    # ------------------------------------------------------------
    print("\n4. TRIGGERING PREDICTION EXPIRY:")

    # predict() performs expiry processing before evaluating
    # new predictions.
    engine.predict({
        "cpu_percent": 25.0,
        "memory": 40.0,
        "disk_percent": 30.0,
        "network_percent": 10.0,
        "anomaly_score": 0.05,
    })

    print("Prediction lifecycle executed.")
    print("PASS")

    # ------------------------------------------------------------
    # 5. VERIFY EXPIRY STATE
    # ------------------------------------------------------------
    print("\n5. VERIFYING EXPIRED PREDICTION STATE:")

    expired_prediction = engine._active_predictions.get(
        prediction_id
    )

    assert expired_prediction is not None

    print(
        "resolved:",
        expired_prediction.resolved,
    )

    print(
        "was_correct:",
        expired_prediction.was_correct,
    )

    assert expired_prediction.resolved is True
    assert expired_prediction.was_correct is False

    print("Prediction marked resolved: PASS")

    # ------------------------------------------------------------
    # 6. VERIFY IT IS NO LONGER ACTIVE
    # ------------------------------------------------------------
    print("\n6. VERIFYING ACTIVE-PREDICTION LIST:")

    active_after = [
        p for p in engine.get_active_predictions()
        if p.prediction_id == prediction_id
    ]

    print(
        "prediction still active:",
        len(active_after) > 0,
    )

    assert len(active_after) == 0

    print("Expired prediction removed from active results: PASS")

    # ------------------------------------------------------------
    # 7. VERIFY NO VALIDATION COUNTING
    # ------------------------------------------------------------
    print("\n7. VERIFYING VALIDATION STATISTICS:")

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

    # Expiry is NOT explicit validation.
    assert (
        crash.validated_predictions
        == initial_validated
    )

    assert (
        crash.correct_predictions
        == initial_correct
    )

    assert (
        crash.detection_accuracy
        == initial_accuracy
    )

    print("validated_predictions unchanged: PASS")
    print("correct_predictions unchanged: PASS")
    print("accuracy unchanged: PASS")

    # ------------------------------------------------------------
    # 8. VERIFY EXPIRED PREDICTION DOES NOT COUNT AS FALSE POSITIVE
    # ------------------------------------------------------------
    print("\n8. VERIFYING EXPIRY IS NOT FALSE-POSITIVE FEEDBACK:")

    print(
        "Before expiry validation count:",
        initial_validated,
    )

    print(
        "After expiry validation count:",
        crash.validated_predictions,
    )

    assert (
        crash.validated_predictions
        == initial_validated
    )

    print(
        "Expired prediction did not enter validation statistics: PASS"
    )

    # ------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------
    print("\n=== RESULT ===")
    print("PREDICTION EXPIRY REGRESSION: PASS")
    print(
        "Expired predictions are resolved but are not "
        "counted as validated outcomes."
    )
    print(
        "Prediction accuracy is protected from expiry-based "
        "statistical distortion."
    )


if __name__ == "__main__":
    main()
