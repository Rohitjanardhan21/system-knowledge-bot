from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILUREDNA CRASH SIGNATURE REPRODUCTION V3 ===")

    engine = FailureDNAEngine()

    print("\n1. CRASH PATTERN:")

    crash = None

    for pattern in engine._patterns.values():
        if getattr(pattern, "pattern_id", None) == "dna_CRASH":
            crash = pattern
            break

    assert crash is not None

    print("pattern_id:", crash.pattern_id)
    print("seen_count:", crash.seen_count)
    print("confidence:", crash.confidence)
    print("signature_steps:", crash.signature_steps)
    print("signature_timing:", crash.signature_timing)

    print("\n2. BUILDING REAL BASELINE:")

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

    print("PASS: baseline populated.")

    print("\n3. ACTUAL BASELINE STATISTICS:")

    for key, value in engine._baseline_stats.items():
        print(key, "=", value)

    print("\n4. SEEDING SIX NORMAL OBSERVATIONS:")

    for _ in range(6):
        metrics = {
            "cpu_percent": 25.0,
            "memory": 40.0,
            "disk_percent": 35.0,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        }

        engine.ingest(metrics)

    assert len(engine._metric_buffer) == 6

    print("Metric buffer size:", len(engine._metric_buffer))
    print("PASS")

    print("\n5. MAPPING SIGNATURE TO ACTUAL BASELINE:")

    # _extract_snapshot() maps raw telemetry names to these
    # internal baseline keys.
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

    means = {}
    stds = {}

    for internal_key in internal_keys:
        stats = engine._baseline_stats[internal_key]

        means[internal_key] = stats["mean"]
        stds[internal_key] = stats["std"]

        print(
            internal_key,
            "| mean=",
            means[internal_key],
            "| std=",
            stds[internal_key],
        )

    print("\n6. FEEDING FOUR CRASH SIGNATURE OBSERVATIONS:")

    for index, step in enumerate(crash.signature_steps, 1):

        internal_values = {}

        for position, internal_key in enumerate(internal_keys):
            internal_values[internal_key] = (
                means[internal_key]
                + step[position] * stds[internal_key]
            )

        metrics = dict(zip(raw_keys, internal_values.values()))

        engine.ingest(metrics)

        current_buffer = list(engine._metric_buffer)

        confidence, eta = engine._match_pattern(
            crash,
            current_buffer,
        )

        print(
            f"Step {index}: "
            f"cpu={metrics['cpu_percent']:.3f} "
            f"memory={metrics['memory']:.3f} "
            f"disk={metrics['disk_percent']:.3f} "
            f"network={metrics['network_percent']:.3f} "
            f"anomaly={metrics['anomaly_score']:.3f} "
            f"buffer={len(current_buffer)} "
            f"confidence={confidence:.4f} "
            f"eta={eta:.2f}"
        )

    print("\n7. FINAL CRASH MATCH:")

    current_buffer = list(engine._metric_buffer)

    confidence, eta = engine._match_pattern(
        crash,
        current_buffer,
    )

    print("Buffer size:", len(current_buffer))
    print("CRASH confidence:", confidence)
    print("CRASH ETA:", eta)

    assert len(current_buffer) >= 10
    assert confidence > 0.0

    print("PASS: CRASH signature matched.")

    print("\nRESULT: CRASH MATCHER REPRODUCTION PASSED.")


if __name__ == "__main__":
    main()
