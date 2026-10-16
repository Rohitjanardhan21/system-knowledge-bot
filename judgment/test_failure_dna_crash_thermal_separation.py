from backend.core.cognitive.failure_dna import FailureDNAEngine


def build_engine():
    engine = FailureDNAEngine()

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

    for _ in range(6):
        engine.ingest({
            "cpu_percent": 25.0,
            "memory": 40.0,
            "disk_percent": 35.0,
            "network_percent": 10.0,
            "anomaly_score": 0.10,
        })

    return engine


def find_pattern(engine, pattern_id):
    for pattern in engine._patterns.values():
        if pattern.pattern_id == pattern_id:
            return pattern
    raise AssertionError(f"Missing pattern: {pattern_id}")


def main():
    print("=== FAILUREDNA CRASH vs THERMAL SEPARATION TEST ===")

    cpu_levels = [
        [1.8, 2.4, 3.1, 4.2],
        [2.0, 2.8, 3.6, 5.0],
        [2.2, 3.2, 4.2, 6.0],
        [2.5, 3.8, 5.0, 8.0],
        [3.0, 4.5, 6.0, 10.0],
    ]

    anomaly_levels = [
        [0.4, 0.7, 1.1, 1.6],
        [0.5, 0.9, 1.4, 2.0],
        [0.6, 1.1, 1.7, 2.5],
        [0.8, 1.4, 2.2, 3.0],
        [1.0, 1.8, 2.8, 4.0],
    ]

    print("\n1. TESTING INCREASING CRASH SEPARATION:")

    for trial, (cpus, anomalies) in enumerate(
        zip(cpu_levels, anomaly_levels),
        1,
    ):
        engine = build_engine()

        crash = find_pattern(engine, "dna_CRASH")
        thermal = find_pattern(engine, "dna_THERMAL")

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

        for i in range(4):

            z_values = [
                cpus[i],
                0.4 + i * 0.2,
                0.3 + i * 0.2,
                0.2 + i * 0.1,
                anomalies[i],
            ]

            values = {
                key: means[key] + z_values[pos] * stds[key]
                for pos, key in enumerate(internal_keys)
            }

            metrics = dict(
                zip(raw_keys, values.values())
            )

            engine.ingest(metrics)

        buffer = list(engine._metric_buffer)

        crash_score, crash_eta = engine._match_pattern(
            crash,
            buffer,
        )

        thermal_score, thermal_eta = engine._match_pattern(
            thermal,
            buffer,
        )

        winner = (
            "CRASH"
            if crash_score > thermal_score
            else "THERMAL"
        )

        print(
            f"Trial {trial}: "
            f"CRASH={crash_score:.6f} "
            f"THERMAL={thermal_score:.6f} "
            f"winner={winner}"
        )

    print("\n2. EXTREME CRASH SIGNAL TEST:")

    engine = build_engine()

    crash = find_pattern(engine, "dna_CRASH")
    thermal = find_pattern(engine, "dna_THERMAL")

    means = {
        key: engine._baseline_stats[key]["mean"]
        for key in ["cpu", "mem", "disk", "net", "anomaly"]
    }

    stds = {
        key: engine._baseline_stats[key]["std"]
        for key in ["cpu", "mem", "disk", "net", "anomaly"]
    }

    for key in stds:
        if stds[key] <= 0:
            stds[key] = 0.1

    extreme = [
        [1.8, 0.4, 0.3, 0.2, 0.4],
        [2.4, 0.6, 0.5, 0.3, 0.7],
        [3.1, 0.8, 0.7, 0.4, 1.1],
        [10.0, 1.0, 0.9, 0.6, 5.0],
    ]

    raw_keys = [
        "cpu_percent",
        "memory",
        "disk_percent",
        "network_percent",
        "anomaly_score",
    ]

    internal_keys = [
        "cpu",
        "mem",
        "disk",
        "net",
        "anomaly",
    ]

    for step in extreme:
        values = {
            key: means[key] + step[pos] * stds[key]
            for pos, key in enumerate(internal_keys)
        }

        engine.ingest(
            dict(zip(raw_keys, values.values()))
        )

    buffer = list(engine._metric_buffer)

    crash_score, crash_eta = engine._match_pattern(
        crash,
        buffer,
    )

    thermal_score, thermal_eta = engine._match_pattern(
        thermal,
        buffer,
    )

    print(
        "Extreme CRASH score:",
        crash_score,
        "ETA:",
        crash_eta,
    )

    print(
        "Extreme THERMAL score:",
        thermal_score,
        "ETA:",
        thermal_eta,
    )

    print("\n3. CONCLUSION:")

    if crash_score > thermal_score:
        print(
            "CRASH CAN OUTRANK THERMAL: "
            "the issue is trajectory construction/signature overlap."
        )
    else:
        print(
            "THERMAL STILL OUTRANKS CRASH: "
            "the matcher has a structural bias toward THERMAL."
        )

    print("\nRESULT: SEPARATION DIAGNOSTIC COMPLETE.")


if __name__ == "__main__":
    main()
