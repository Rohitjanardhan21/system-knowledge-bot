from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILUREDNA CRASH-DOMINANT TRAJECTORY TEST ===")

    engine = FailureDNAEngine()

    print("\n1. BUILDING BASELINE:")

    engine._baseline_stats = {}
    engine._metric_buffer.clear()

    for i in range(30):
        metrics = {
            "cpu_percent": 25.0 + (i % 3) * 0.2,
            "memory": 40.0 + (i % 2) * 0.2,
            "disk_percent": 35.0 + (i % 2) * 0.2,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        }

        engine._update_baseline(
            engine._extract_snapshot(metrics)
        )

    print("PASS")

    print("\n2. FINDING CRASH PATTERN:")

    crash = None

    for pattern in engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == "dna_CRASH":
            crash = pattern
            break

    assert crash is not None

    print("CRASH signature:", crash.signature_steps)
    print("PASS")

    print("\n3. SEEDING SIX NORMAL OBSERVATIONS:")

    normal = {
        "cpu_percent": 25.0,
        "memory": 40.0,
        "disk_percent": 35.0,
        "network_percent": 10.0,
        "anomaly_score": 0.10,
    }

    for _ in range(6):
        engine.ingest(normal)

    assert len(engine._metric_buffer) == 6

    print("Buffer:", len(engine._metric_buffer))
    print("PASS")

    print("\n4. BUILDING CRASH-DOMINANT TRAJECTORY:")

    internal_keys = [
        "cpu",
        "mem",
        "disk",
        "net",
        "anomaly",
    ]

    raw_keys = [
        "cpu_percent",
        "memory",
        "disk_percent",
        "network_percent",
        "anomaly_score",
    ]

    means = {
        key: engine._baseline_stats[key]["mean"]
        for key in internal_keys
    }

    stds = {
        key: engine._baseline_stats[key]["std"]
        for key in internal_keys
    }

    for key in internal_keys:
        if stds[key] <= 0:
            stds[key] = 0.1

    # Preserve the CRASH progression but make the terminal
    # CPU/anomaly signal more distinctive than THERMAL.
    trajectory = [
        [1.8, 0.4, 0.3, 0.2, 0.4],
        [2.4, 0.6, 0.5, 0.3, 0.7],
        [3.1, 0.8, 0.7, 0.4, 1.1],
        [4.8, 1.0, 0.9, 0.6, 2.0],
    ]

    for index, step in enumerate(trajectory, 1):

        internal_values = {
            key: means[key] + step[position] * stds[key]
            for position, key in enumerate(internal_keys)
        }

        metrics = dict(
            zip(
                raw_keys,
                internal_values.values(),
            )
        )

        engine.ingest(metrics)

        print(
            f"Step {index}: "
            f"cpu={metrics['cpu_percent']:.3f} "
            f"mem={metrics['memory']:.3f} "
            f"disk={metrics['disk_percent']:.3f} "
            f"net={metrics['network_percent']:.3f} "
            f"anomaly={metrics['anomaly_score']:.3f}"
        )

    print("\n5. BUFFER:")

    current_buffer = list(engine._metric_buffer)

    print("Buffer:", len(current_buffer))

    assert len(current_buffer) == 10

    print("PASS")

    print("\n6. ALL PATTERN SCORES:")

    scores = []

    for pattern in engine._patterns.values():

        confidence, eta = engine._match_pattern(
            pattern,
            current_buffer,
        )

        scores.append(
            (
                confidence,
                pattern.pattern_id,
                eta,
            )
        )

        print(
            f"{pattern.pattern_id}: "
            f"confidence={confidence:.6f} "
            f"eta={eta:.2f}"
        )

    scores.sort(reverse=True)

    print("\n7. RANKING:")

    for rank, (confidence, pattern_id, eta) in enumerate(scores, 1):
        print(
            f"#{rank}: "
            f"{pattern_id} "
            f"confidence={confidence:.6f} "
            f"eta={eta:.2f}"
        )

    winner = scores[0][1]

    print("\nWinner:", winner)

    print("\n8. ACTUAL predict():")

    final = current_buffer[-1]

    final_metrics = {
        "cpu_percent": final["cpu"],
        "memory": final["mem"],
        "disk_percent": final["disk"],
        "network_percent": final["net"],
        "anomaly_score": final["anomaly"],
    }

    print("Final metrics:", final_metrics)

    prediction = engine.predict(final_metrics)

    assert prediction is not None

    print(
        "prediction_id:",
        prediction.prediction_id,
    )

    print(
        "failure_type:",
        prediction.failure_type,
    )

    print(
        "confidence:",
        prediction.confidence,
    )

    print(
        "minutes_remaining:",
        prediction.minutes_remaining,
    )

    print("\n9. ASSERTING CRASH DOMINANCE:")

    assert winner == "dna_CRASH", (
        f"Expected CRASH to win, but {winner} won."
    )

    assert prediction.failure_type == "CRASH", (
        f"Expected predict() CRASH, got {prediction.failure_type}."
    )

    print("PASS: CRASH is the dominant learned pattern.")

    print("\nRESULT: CRASH-DOMINANT TRAJECTORY PASSED.")


if __name__ == "__main__":
    main()
