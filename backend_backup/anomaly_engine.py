from backend.baseline_engine import compute_baseline, compute_disk_growth

Z_SPIKE = 3.0


def detect_anomalies(current):

    anomalies = []

    # --------------------------------------------------
    # 🔥 METRICS
    # --------------------------------------------------
    metric_map = {
        "cpu": current.get("cpu", 0),
        "memory": current.get("memory", 0),
        "disk": current.get("disk", 0)
    }

    # 🔥 PRELOAD BASELINES (IMPORTANT OPTIMIZATION)
    baselines = {
        m: compute_baseline(m)
        for m in metric_map
    }

    # --------------------------------------------------
    # 🔥 Z-SCORE DETECTION
    # --------------------------------------------------
    for metric, value in metric_map.items():

        base = baselines.get(metric)

        if not base:
            continue

        mean = base.get("mean", 0)
        std = base.get("std", 0)

        # 🔥 avoid noise
        if std == 0 or value < 5:
            continue

        try:
            z = abs(value - mean) / std
        except:
            continue

        if z >= Z_SPIKE:

            severity = "critical" if z > 4 else "warning"

            anomalies.append({
                "type": f"{metric}_anomaly",  # 🔥 unified naming
                "metric": metric,
                "value": round(value, 2),
                "baseline": round(mean, 2),
                "z_score": round(z, 2),
                "severity": severity,
                "confidence": round(min(1.0, z / 5), 2)
            })

    # --------------------------------------------------
    # 🔥 MEMORY LEAK (IMPROVED TREND)
    # --------------------------------------------------
    mem_base = baselines.get("memory")

    if mem_base:
        latest = mem_base.get("latest", 0)
        mean = mem_base.get("mean", 0)

        # 🔥 deviation from baseline
        drift = latest - mean

        if drift > 15:
            anomalies.append({
                "type": "memory_drift",
                "metric": "memory",
                "value": latest,
                "baseline": mean,
                "severity": "warning",
                "confidence": 0.75
            })

    # --------------------------------------------------
    # 🔥 DISK GROWTH
    # --------------------------------------------------
    disk_growth = compute_disk_growth()

    if disk_growth and disk_growth.get("delta", 0) > 5:
        anomalies.append({
            "type": "disk_growth",
            "metric": "disk",
            "delta": round(disk_growth["delta"], 2),
            "rate": disk_growth.get("rate", 0),
            "severity": "critical" if disk_growth["delta"] > 15 else "warning",
            "confidence": 0.8
        })

    # --------------------------------------------------
    # 🔥 HARD THRESHOLD (CRITICAL FAILSAFE)
    # --------------------------------------------------
    if current.get("cpu", 0) > 95:
        anomalies.append({
            "type": "cpu_overload",
            "metric": "cpu",
            "value": current["cpu"],
            "severity": "critical",
            "confidence": 0.95
        })

    # --------------------------------------------------
    # 🔥 NETWORK (RELATIVE DETECTION)
    # --------------------------------------------------
    net = current.get("network", {})
    throughput = net.get("throughput", 0)

    # 🔥 dynamic baseline (simple heuristic)
    if throughput > 50:  # safer default
        anomalies.append({
            "type": "network_spike",
            "metric": "network",
            "value": throughput,
            "severity": "warning",
            "confidence": 0.7
        })

    # --------------------------------------------------
    # 🔥 DEDUPLICATION (IMPORTANT)
    # --------------------------------------------------
    unique = {}
    for a in anomalies:
        key = f"{a['type']}:{a.get('metric')}"
        if key not in unique:
            unique[key] = a

    return list(unique.values())
