from backend.baseline_engine import compute_baseline, compute_disk_growth

Z_SPIKE = 3.0


def detect_anomalies(current):
    anomalies = []

    for metric in ["cpu_pct", "mem_pct", "network"]:
        base = compute_baseline(metric)

        if not base or base["std"] == 0:
            continue

        z = abs(current[metric] - base["mean"]) / base["std"]

        if z >= Z_SPIKE:
            severity = "high" if z > 4 else "medium"

            anomalies.append({
                "type": f"{metric}_spike",
                "metric": metric,
                "value": current[metric],
                "baseline": base["mean"],
                "z": round(z, 2),
                "severity": severity,
                "confidence": min(1.0, z / 5),
            })

    # Memory leak detection
    mem_base = compute_baseline("mem_pct")
    if mem_base:
        slope = mem_base["latest"] - mem_base["min"]
        if slope > 15:
            anomalies.append({
                "type": "memory_leak_pattern",
                "metric": "mem_pct",
                "value": mem_base["latest"],
                "baseline": mem_base["mean"],
                "severity": "medium",
                "confidence": 0.75,
            })

    # Disk growth
    disk_growth = compute_disk_growth()
    if disk_growth and disk_growth["delta"] > 5:
        anomalies.append({
            "type": "disk_growth",
            "metric": "disk_pct",
            "delta": disk_growth["delta"],
            "rate": disk_growth["rate"],
            "severity": "medium" if disk_growth["delta"] < 15 else "high",
            "confidence": 0.8,
        })

    return anomalies
