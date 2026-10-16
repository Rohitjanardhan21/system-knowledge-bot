import time

from backend.core.cognitive.failure_dna import (
    FailureDNAEngine,
    ActivePrediction,
)


def main():
    print("=== FAILUREDNA PREDICTION VALIDATION FEEDBACK REGRESSION V5 ===")

    engine = FailureDNAEngine()

    # ------------------------------------------------------------
    # 1. FIND CRASH PATTERN
    # ------------------------------------------------------------
    print("\n1. FINDING CRASH PATTERN:")

    crash = None

    for pattern in engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == "dna_CRASH":
            crash = pattern
            break

    assert crash is not None, "CRASH pattern not found"

    print("Initial seen_count:", crash.seen_count)
    print("Initial confidence:", crash.confidence)
    print("Initial detection_accuracy:", crash.detection_accuracy)
    print("Initial validated_predictions:", crash.validated_predictions)
    print("Initial correct_predictions:", crash.correct_predictions)

    initial_validated = crash.validated_predictions
    initial_correct = crash.correct_predictions

    print("PASS")

    # ------------------------------------------------------------
    # 2. CREATE SYNTHETIC ACTIVE PREDICTION
    # ------------------------------------------------------------
    print("\n2. CREATING SYNTHETIC ACTIVE PREDICTION:")

    prediction_id = f"pred_validation_feedback_v5_{time.time_ns()}"

    prediction = ActivePrediction(
        prediction_id=prediction_id,
        failure_type="CRASH",
        detected_at=time.time(),
        predicted_eta=time.time() + 300,
        confidence=0.91,
        minutes_remaining=5.0,
        plain_message="Synthetic crash prediction",
        plain_action="Save your work and restart the affected application",
        severity="HIGH",
        pattern_id="dna_CRASH",
    )

    print("prediction_id:", prediction.prediction_id)
    print("pattern_id:", prediction.pattern_id)
    print("failure_type:", prediction.failure_type)
    print("confidence:", prediction.confidence)
    print("resolved:", prediction.resolved)
    print("was_correct:", prediction.was_correct)

    assert prediction.resolved is False
    assert prediction.was_correct is None

    print("PASS")

    # ------------------------------------------------------------
    # 3. REGISTER PREDICTION
    # ------------------------------------------------------------
    print("\n3. REGISTERING PREDICTION:")

    engine._active_predictions[prediction_id] = prediction

    active = engine.get_active_predictions()

    found = [
        p for p in active
        if p.prediction_id == prediction_id
    ]

    assert len(found) == 1, "Prediction was not registered"

    print("Prediction registered:", True)
    print("Active prediction count:", len(active))
    print("PASS")

    # ------------------------------------------------------------
    # 4. RESOLVE AS TRUE POSITIVE
    # ------------------------------------------------------------
    print("\n4. RESOLVING AS TRUE POSITIVE:")

    result = engine.resolve_prediction(
        prediction_id,
        True,
    )

    print("resolve_prediction() returned:", result)

    # ------------------------------------------------------------
    # 5. VERIFY PREDICTION STATE
    # ------------------------------------------------------------
    print("\n5. VERIFYING PREDICTION STATE:")

    resolved_prediction = engine._active_predictions.get(
        prediction_id
    )

    assert resolved_prediction is not None

    print("resolved:", resolved_prediction.resolved)
    print("was_correct:", resolved_prediction.was_correct)

    assert resolved_prediction.resolved is True
    assert resolved_prediction.was_correct is True

    print("PASS")

    # ------------------------------------------------------------
    # 6. VERIFY LEARNING FEEDBACK
    # ------------------------------------------------------------
    print("\n6. VERIFYING CRASH PATTERN VALIDATION FEEDBACK:")

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

    assert crash.validated_predictions == initial_validated + 1
    assert crash.correct_predictions == initial_correct + 1

    assert crash.detection_accuracy is not None

    expected_accuracy = (
        crash.correct_predictions /
        crash.validated_predictions
    )

    print(
        "expected_accuracy:",
        expected_accuracy,
    )

    assert abs(
        crash.detection_accuracy - expected_accuracy
    ) < 1e-9

    print("PASS")

    # ------------------------------------------------------------
    # 7. VERIFY TRUSTWORTHINESS
    # ------------------------------------------------------------
    print("\n7. VERIFYING TRUSTWORTHINESS:")

    trustworthy = engine.is_prediction_trustworthy(
        "dna_CRASH"
    )

    print("CRASH pattern trustworthy:", trustworthy)

    assert trustworthy is True

    print("PASS")

    # ------------------------------------------------------------
    # 8. VERIFY DNA SUMMARY
    # ------------------------------------------------------------
    print("\n8. VERIFYING DNA SUMMARY:")

    summary = engine.get_dna_summary()

    crash_summary = None

    for pattern in summary.get("pattern_list", []):
        if pattern.get("type") == "CRASH":
            crash_summary = pattern
            break

    assert crash_summary is not None

    print("CRASH summary:", crash_summary)

    assert crash_summary["accuracy"] is not None
    assert crash_summary["trustworthy"] is True

    print("PASS")

    # ------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------
    print("\n=== RESULT ===")
    print("TRUE-POSITIVE VALIDATION FEEDBACK: PASS")
    print("Prediction resolution works.")
    print("Validation counters updated.")
    print("Detection accuracy updated.")
    print("Trustworthiness updated.")
    print("DNA summary updated.")


if __name__ == "__main__":
    main()
