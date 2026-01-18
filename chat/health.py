def evaluate_memory(memory):
    total = memory["total_mb"]
    available = memory["available_mb"]

    available_pct = (available / total) * 100

    if available_pct < 10:
        return "critical", available_pct
    elif available_pct < 25:
        return "high", available_pct
    else:
        return "normal", available_pct


def evaluate_disk(storage):
    # Evaluate root filesystem
    for fs in storage["filesystems"]:
        if fs["mount_point"] == "/":
            used_pct = (fs["used_gb"] / fs["size_gb"]) * 100

            if used_pct > 90:
                return "critical", used_pct
            elif used_pct > 75:
                return "high", used_pct
            else:
                return "normal", used_pct


def overall_health(memory_status, disk_status):
    if "critical" in (memory_status, disk_status):
        return "degraded"
    if "high" in (memory_status, disk_status):
        return "warning"
    return "healthy"


    return "unknown", None


