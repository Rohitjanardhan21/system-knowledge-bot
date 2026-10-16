from __future__ import annotations

import json

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILURE-DNA CRASH PREDICTION TEST ===")

    engine = FailureDNAEngine()

    print("\n=== CURRENT CRASH PATTERN ===")

    summary = engine.get_dna_summary()

    crash_patterns = [
        p for p in summary.get("pattern_list", [])
        if str(p.get("type", "")).upper() == "CRASH"
    ]

    print(json.dumps(crash_patterns, indent=2, default=str))

    assert crash_patterns, "No CRASH pattern available"

    crash = crash_patterns[0]

    print("\nCRASH seen:", crash.get("seen"))
    print("CRASH confidence:", crash.get("confidence"))
    print("CRASH trustworthy:", crash.get("trustworthy"))

    print("\n=== FEEDING TRAJECTORY ===")

    trajectory = [
        {
            "cpu": 25.0,
            "memory": 40.0,
            "disk": 35.0,
            "temperature": 45.0,
            "anomaly_score": 0.10,
        },
        {
            "cpu": 45.0,
            "memory": 42.0,
            "disk": 35.0,
            "temperature": 48.0,
            "anomaly_score": 0.20,
        },
        {
            "cpu": 65.0,
            "memory": 44.0,
            "disk": 35.0,
            "temperature": 50.0,
            "anomaly_score": 0.35,
        },
        {
            "cpu": 80.0,
            "memory": 46.0,
            "disk": 35.0,
            "temperature": 52.0,
            "anomaly_score": 0.55,
        },
        {
            "cpu": 90.0,
            "memory": 48.0,
            "disk": 35.0,
            "temperature": 54.0,
            "anomaly_score": 0.75,
        },
        {
            "cpu": 97.0,
            "memory": 50.0,
            "disk": 35.0,
            "temperature": 56.0,
            "anomaly_score": 0.90,
        },
    ]

    prediction = None

    for index, metrics in enumerate(trajectory, 1):
        prediction = engine.predict(metrics)

        print(f"\n--- Observation {index} ---")
        print("Metrics:", metrics)

        if prediction is None:
            print("Prediction: None")
            continue

        print("Prediction ID:", getattr(prediction, "prediction_id", None))
        print("Failure type:", getattr(prediction, "failure_type", None))
        print("Confidence:", getattr(prediction, "confidence", None))
        print("Minutes remaining:", getattr(prediction, "minutes_remaining", None))
        print("Severity:", getattr(prediction, "severity", None))
        print("Pattern ID:", getattr(prediction, "pattern_id", None))
        print("Message:", getattr(prediction, "plain_message", None))
        print("Action:", getattr(prediction, "plain_action", None))

    print("\n==============================================")

    if prediction is None:
        print("RESULT: NO CRASH PREDICTION GENERATED")
        print("The learned CRASH pattern exists, but the supplied trajectory")
        print("does not satisfy its matching conditions.")
    else:
        print("RESULT: CRASH PREDICTION GENERATED")
        print("Failure type:", getattr(prediction, "failure_type", None))
        print("Confidence:", getattr(prediction, "confidence", None))
        print("Pattern:", getattr(prediction, "pattern_id", None))

    print("==============================================")


if __name__ == "__main__":
    main()
