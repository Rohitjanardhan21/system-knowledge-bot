from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILUREDNA PATTERN COMPETITION DIAGNOSTIC ===")

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

    print("\n2. LOCATING LEARNED PATTERNS:")

    for pattern in engine._patterns.values():
        print(
            pattern.pattern_id,
            "| seen=",
            pattern.seen_count,
            "| confidence=",
            pattern.confidence,
            "| signature_steps=",
            pattern.signature_steps,
        )

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

    print("Buffer:", len(engine._metric_buffer))
    assert len(engine._metric_buffer) == 6

    print("PASS")

    print("\n4. REPLAYING CRASH SIGNATURE:")

    crash = None

    for pattern in engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == "dna_CRASH":
            crash = pattern
            break

    assert crash is not None

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

    for index, step in enumerate(crash.signature_steps, 1):

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

    print("\n5. BUFFER SIZE:")

    current_buffer = list(engine._metric_buffer)

    print("Buffer:", len(current_buffer))

    assert len(current_buffer) == 10

    print("PASS")

    print("\n6. COMPETING PATTERN SCORES:")

    scores = []

    for pattern in engine._patterns.values():

        try:
            confidence, eta = engine._match_pattern(
                pattern,
                current_buffer,
            )
        except Exception as exc:
            print(
                pattern.pattern_id,
                "ERROR:",
                type(exc).__name__,
                str(exc),
            )
            continue

        scores.append(
            (
                confidence,
                pattern.pattern_id,
                eta,
                pattern.seen_count,
                pattern.confidence,
            )
        )

        print(
            f"{pattern.pattern_id}: "
            f"confidence={confidence:.6f} "
            f"eta={eta:.2f} "
            f"seen={pattern.seen_count} "
            f"learned_confidence={pattern.confidence}"
        )

    print("\n7. SORTED COMPETITION:")

    scores.sort(reverse=True)

    for rank, item in enumerate(scores, 1):
        confidence, pattern_id, eta, seen, learned_confidence = item

        print(
            f"#{rank} "
            f"{pattern_id} "
            f"confidence={confidence:.6f} "
            f"eta={eta:.2f}"
        )

    print("\n8. ACTUAL PREDICT() RESULT:")

    final_snapshot = current_buffer[-1]

    final_metrics = {
        "cpu_percent": final_snapshot["cpu"],
        "memory": final_snapshot["mem"],
        "disk_percent": final_snapshot["disk"],
        "network_percent": final_snapshot["net"],
        "anomaly_score": final_snapshot["anomaly"],
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

    print("\n9. DIAGNOSTIC CONCLUSION:")

    winner = scores[0][1]

    print("Matcher winner:", winner)
    print("predict() winner:", prediction.failure_type)

    if winner != prediction.failure_type:
        print(
            "WARNING: predict() applies additional selection/filtering "
            "beyond the raw _match_pattern scores."
        )

    print("\nRESULT: COMPETITION DIAGNOSTIC COMPLETE.")


if __name__ == "__main__":
    main()
