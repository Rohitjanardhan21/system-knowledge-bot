def analyze_slowness(memory, storage):
    reasons = []
    confidence = []

    # -------------------------
    # Memory-based reasoning
    # -------------------------
    total = memory["total_mb"]
    available = memory["available_mb"]
    available_pct = (available / total) * 100

    if available_pct < 10:
        reasons.append(
            "Available memory is critically low, which can cause applications to freeze or be terminated."
        )
        confidence.append("high")
    elif available_pct < 25:
        reasons.append(
            "Available memory is low, which can slow down multitasking and app switching."
        )
        confidence.append("medium")

    # -------------------------
    # Disk-based reasoning
    # -------------------------
    for fs in storage["filesystems"]:
        if fs["mount_point"] == "/":
            used_pct = (fs["used_gb"] / fs["size_gb"]) * 100

            if used_pct > 90:
                reasons.append(
                    "The main disk is almost full, which can severely slow down the system and cause failures."
                )
                confidence.append("high")
            elif used_pct > 75:
                reasons.append(
                    "Disk usage is high, which can reduce system responsiveness."
                )
                confidence.append("medium")

    # -------------------------
    # No strong signals
    # -------------------------
    if not reasons:
        reasons.append(
            "There are no obvious resource bottlenecks right now. Slowness may be workload-specific or temporary."
        )
        confidence.append("low")

    return reasons, confidence
