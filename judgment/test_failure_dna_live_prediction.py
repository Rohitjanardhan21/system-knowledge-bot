from __future__ import annotations

import json

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILURE-DNA LIVE BASELINE + CRASH PREDICTION TEST ===")

    engine = FailureDNAEngine()

    crash_pattern = engine._patterns.get("dna_CRASH")

    assert crash_pattern is not None, "dna_CRASH pattern not loaded"

    print("\n=== LOADED CRASH PATTERN ===")
    print("Seen:", crash_pattern.seen_count)
    print("Confidence:", crash_pattern.confidence)
    print("Signature:", json.dumps(
        crash_pattern.signature_steps,
        indent=2,
    ))

    print("\n=== BUILDING BASELINE ===")

    baseline_samples = [
        {
            "cpu_percent": 25.0,
            "memory": 40.0,
            "disk_percent": 35.0,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        },
        {
            "cpu_percent": 27.0,
            "memory": 41.0,
            "disk_percent": 36.0,
            "network_percent": 11.0,
            "anomaly_score": 0.11,
        },
        {
            "cpu_percent": 24.0,
            "memory": 39.0,
            "disk_percent": 34.0,
            "network_percent": 9.0,
            "anomaly_score": 0.09,
        },
        {
            "cpu_percent": 26.0,
            "memory": 40.0,
            "disk_percent": 35.0,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        },
        {
            "cpu_percent": 25.0,
            "memory": 41.0,
            "disk_percent": 35.0,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        },
        {
            "cpu_percent": 26.0,
            "memory": 40.0,
            "disk_percent": 36.0,
            "network_percent": 10.0,
            "anomaly_score": 0.11,
        },
        {
            "cpu_percent": 24.0,
            "memory": 40.0,
            "disk_percent": 35.0,
            "network_percent": 9.0,
            "anomaly_score": 0.09,
        },
        {
            "cpu_percent": 25.0,
            "memory": 39.0,
            "disk_percent": 34.0,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        },
        {
            "cpu_percent": 27.0,
            "memory": 41.0,
            "disk_percent": 36.0,
            "network_percent": 11.0,
            "anomaly_score": 0.12,
        },
        {
            "cpu_percent": 25.0,
            "memory": 40.0,
            "disk_percent": 35.0,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        },
    ]

    for metrics in baseline_samples:
        snapshot = engine._extract_snapshot(metrics)
        engine._update_baseline(snapshot)

    print(json.dumps(engine._baseline_stats, indent=2))

    assert engine._baseline_stats, "Baseline was not populated"

    print("\n=== FEEDING CRASH TRAJECTORY ===")

    # Use the learned CRASH signature directly as target z-scores.
    # Convert each target z-score into raw metrics using the baseline.
    signature = crash_pattern.signature_steps

    key_order = [
        ("cpu", "cpu_percent"),
        ("mem", "memory"),
        ("disk", "disk_percent"),
        ("net", "network_percent"),
        ("anomaly", "anomaly_score"),
    ]

    prediction = None

    # Need at least 10 observations for _match_pattern().
    observations = [
        [0.2, 0.0, 0.0, 0.0, 0.0],
        [0.4, 0.1, 0.0, 0.0, 0.05],
        [0.6, 0.1, 0.1, 0.0, 0.10],
        [0.9, 0.2, 0.1, 0.1, 0.15],
        signature[0],
        [2.1, 0.5, 0.4, 0.25, 0.5],
        signature[1],
        [2.8, 0.7, 0.6, 0.35, 0.9],
        signature[2],
        [3.6, 0.9, 0.8, 0.5, 1.3],
        signature[3],
        [4.4, 1.1, 1.0, 0.65, 1.7],
    ]

    for index, target_z in enumerate(observations, 1):
        metrics = {}

        for (internal_key, source_key), z in zip(
            key_order,
            target_z,
        ):
            stats = engine._baseline_stats[internal_key]

            mean = float(stats["mean"])
            std = max(0.1, float(stats["std"]))

            metrics[source_key] = mean + float(z) * std

        prediction = engine.predict(metrics)

        actual_snapshot = engine._extract_snapshot(metrics)
        actual_z = engine._to_z_scores(actual_snapshot)

        print(f"\n--- Observation {index} ---")
        print("Target Z:", [round(float(x), 3) for x in target_z])
        print("Actual Z:", [round(float(x), 3) for x in actual_z])

        if prediction is None:
            print("Prediction: None")
        else:
            print("Prediction ID:", prediction.prediction_id)
            print("Failure type:", prediction.failure_type)
            print("Confidence:", prediction.confidence)
            print("Minutes remaining:", prediction.minutes_remaining)
            print("Severity:", prediction.severity)
            print("Pattern ID:", prediction.pattern_id)
            print("Action:", prediction.plain_action)

    print("\n==============================================")

    if prediction is None:
        print("RESULT: NO CRASH PREDICTION GENERATED")
    else:
        print("RESULT: CRASH PREDICTION GENERATED")
        print("Failure type:", prediction.failure_type)
        print("Confidence:", prediction.confidence)
        print("Minutes remaining:", prediction.minutes_remaining)

        assert str(prediction.failure_type).upper() == "CRASH"
        assert prediction.pattern_id == "dna_CRASH"
        assert prediction.confidence >= 0.70

    print("==============================================")


if __name__ == "__main__":
    main()
