"""
Metric Normalizer

Converts nested collector output into flat metrics
used by reasoning engines.
"""

def normalize_metrics(snapshot: dict):
    metrics = snapshot.get("metrics", {})

    # ---------------- CPU ----------------
    cpu_pct = metrics.get("cpu", {}).get("usage_percent", 0)

    # ---------------- MEMORY ----------------
    mem_pct = metrics.get("memory", {}).get("percent", 0)

    # ---------------- DISK ----------------
    disk_pct = 0
    disks = metrics.get("disk", [])

    if isinstance(disks, list) and disks:
        # prioritize root mount
        root_disk = next(
            (
                d for d in disks
                if d.get("mount") == "/" and d.get("device", "").startswith("/dev")
            ),
            None
        )

        if root_disk:
            disk_pct = root_disk.get("percent", 0)
        else:
            # fallback: first real device (ignore loop + snap)
            for d in disks:
                device = d.get("device", "")
                if device.startswith("/dev") and "loop" not in device:
                    disk_pct = d.get("percent", 0)
                    break

    # ---------------- NETWORK ----------------
    network_recv = metrics.get("network", {}).get("bytes_recv", 0)

    return {
        "cpu_pct": round(cpu_pct, 2),
        "mem_pct": round(mem_pct, 2),
        "disk_pct": round(disk_pct, 2),
        "network": network_recv,
    }
