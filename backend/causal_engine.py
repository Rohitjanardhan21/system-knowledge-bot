# ---------------------------------------------------------
# CAUSAL ENGINE
# ---------------------------------------------------------

"""
Determines WHY the system is behaving the way it is.

Uses:
- Temporal patterns (trend behavior)
- Metric relationships (CPU vs Memory vs Disk)

Outputs:
- cause type
- confidence
- reasoning string
"""

# ---------------------------------------------------------
# RULES CONFIG
# ---------------------------------------------------------

HIGH_CPU = 80
HIGH_MEM = 75
HIGH_DISK = 85


# ---------------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------------

def detect_causal_relationship(flat_metrics, temporal):
    cpu = flat_metrics.get("cpu_pct", 0)
    mem = flat_metrics.get("mem_pct", 0)
    disk = flat_metrics.get("disk_pct", 0)

    cpu_pattern = temporal.get("cpu", {}).get("pattern")
    mem_pattern = temporal.get("memory", {}).get("pattern")
    disk_pattern = temporal.get("disk", {}).get("pattern")

    causes = []

    # ---------------------------
    # CPU Overload
    # ---------------------------
    if cpu > HIGH_CPU:
        causes.append({
            "type": "cpu_overload",
            "confidence": 0.8,
            "reason": "CPU usage is above threshold indicating heavy computation load"
        })

    # ---------------------------
    # Memory Pressure → CPU Impact
    # ---------------------------
    if mem > HIGH_MEM and cpu > 60:
        if mem_pattern == "gradual_increase" and cpu_pattern in ["gradual_increase", "spike"]:
            causes.append({
                "type": "memory_pressure",
                "confidence": 0.85,
                "reason": "Memory increased before CPU, indicating possible swapping or GC overhead"
            })

    # ---------------------------
    # Disk Bottleneck
    # ---------------------------
    if disk > HIGH_DISK and cpu_pattern == "oscillation":
        causes.append({
            "type": "disk_io_bottleneck",
            "confidence": 0.75,
            "reason": "Disk usage high with CPU fluctuation, likely IO wait bottleneck"
        })

    # ---------------------------
    # Sustained Workload
    # ---------------------------
    if cpu_pattern == "gradual_increase" and mem_pattern == "stable":
        causes.append({
            "type": "sustained_compute_load",
            "confidence": 0.7,
            "reason": "CPU rising steadily without memory pressure suggests continuous workload"
        })

    # ---------------------------
    # Idle / Stable
    # ---------------------------
    if cpu < 40 and mem < 50:
        causes.append({
            "type": "normal_operation",
            "confidence": 0.9,
            "reason": "System operating within normal parameters"
        })

    # ---------------------------
    # FALLBACK
    # ---------------------------
    if not causes:
        return {
            "type": "unknown",
            "confidence": 0.4,
            "reason": "No clear causal pattern detected"
        }

    # Return highest confidence cause
    causes.sort(key=lambda x: x["confidence"], reverse=True)
    return causes[0]
