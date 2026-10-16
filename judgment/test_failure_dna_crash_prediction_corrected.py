from __future__ import annotations

import json

import numpy as np

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILURE-DNA CRASH PREDICTION — CORRECT METRIC CONTRACT ===")

    engine = FailureDNAEngine()

    print("\n=== BASELINE STATS ===")
    print(json.dumps(engine._baseline_stats, indent=2, default=str))

    print("\n=== CRASH PATTERN ===")

    crash_patterns = [
        pattern
        for pattern in engine._patterns.values()
        if str(pattern.failure_type).upper() == "CRASH"
    ]

    assert crash_patterns, "CRASH pattern not found"

    pattern = crash_patterns[0]

    print("Pattern ID:", pattern.pattern_id)
    print("Seen:", pattern.seen_count)
    print("Confidence:", pattern.confidence)
    print("Signature steps:")
    print(json.dumps(pattern.signature_steps, indent=2))
    print("Signature timing:", pattern.signature_timing)

    print("\n=== CURRENT Z-SCORE CONVERSION ===")

    def inverse_z(key, z):
        stats = engine._baseline_stats.get(key)

        if not isinstance(stats, dict):
            raise AssertionError(
                f"Missing baseline statistics for '{key}': {stats}"
            )

        mean = float(stats.get("mean", 0.0))
        std = float(stats.get("std", 1.0))

        if std <= 0:
            std = 1.0

        return mean + z * std

    # Pattern dimensions are:
    # CPU, memory, disk, network, anomaly
    metric_keys = [
        "cpu",
        "mem",
        "disk",
        "net",
        "anomaly",
    ]

    source_keys = {
        "cpu": "cpu_percent",
        "mem": "memory",
        "disk": "disk_percent",
        "net": "network_percent",
        "anomaly": "anomaly_score",
    }

    print("\n=== CONSTRUCTING SIGNATURE-MATCHING OBSERVATIONS ===")

    # Need >= 10 observations because _match_pattern() requires
    # len(current_buffer) >= 10.
    #
    # First 6 observations provide the rising trajectory.
    # Final observations approximate the learned CRASH signature.
    target_z = [
        [0.4, 0.1, 0.1, 0.1, 0.1],
        [0.8, 0.2, 0.1, 0.1, 0.1],
        [1.2, 0.3, 0.2, 0.1, 0.2],
        [1.6, 0.3, 0.2, 0.2, 0.3],
        [1.8, 0.4, 0.3, 0.2, 0.4],
        [2.1, 0.5, 0.4, 0.25, 0.5],
        [2.4, 0.6, 0.5, 0.3, 0.7],
        [2.8, 0.7, 0.6, 0.35, 0.9],
        [3.1, 0.8, 0.7, 0.4, 1.1],
        [3.6, 0.9, 0.8, 0.5, 1.3],
        [4.2, 1.0, 0.9, 0.6, 1.6],
        [4.4, 1.1, 1.0, 0.65, 1.7],
    ]

    prediction = None

    for index, z_values in enumerate(target_z, 1):
        metrics = {}

        for key, z in zip(metric_keys, z_values):
            metrics[source_keys[key]] = inverse_z(key, z)

        # Make sure anomaly is included under the actual expected key.
        metrics["anomaly_score"] = inverse_z(
            "anomaly",
            z_values[4],
        )

        actual_snapshot = engine._extract_snapshot(metrics)
        actual_z = engine._to_z_scores(actual_snapshot)

        prediction = engine.predict(metrics)

        print(f"\n--- Observation {index} ---")
        print("Target Z:", [round(float(x), 3) for x in z_values])
        print("Actual Z:", [round(float(x), 3) for x in actual_z])
        print("CPU:", round(metrics["cpu_percent"], 3))
        print("Memory:", round(metrics["memory"], 3))
        print("Disk:", round(metrics["disk_percent"], 3))
        print("Anomaly:", round(metrics["anomaly_score"], 3))

        if prediction is None:
            print("Prediction: None")
        else:
            print("Prediction ID:", prediction.prediction_id)
            print("Failure type:", prediction.failure_type)
            print("Confidence:", prediction.confidence)
            print("Minutes remaining:", prediction.minutes_remaining)
            print("Severity:", prediction.severity)
            print("Pattern ID:", prediction.pattern_id)
            print("Message:", prediction.plain_message)
            print("Action:", prediction.plain_action)

    print("\n==============================================")

    if prediction is None:
        print("RESULT: NO CRASH PREDICTION")
        print("The trajectory still did not satisfy the learned matcher.")
    else:
        print("RESULT: CRASH PREDICTION GENERATED")
        print("Failure type:", prediction.failure_type)
        print("Confidence:", prediction.confidence)
        print("Minutes remaining:", prediction.minutes_remaining)
        print("Pattern:", prediction.pattern_id)

        assert str(prediction.failure_type).upper() == "CRASH"
        assert prediction.pattern_id == pattern.pattern_id
        assert prediction.confidence >= 0.70

    print("==============================================")


if __name__ == "__main__":
    main()
