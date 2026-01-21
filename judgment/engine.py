# ==========================================================
# System Knowledge Bot — Judgment Engine (DEFENSIVE)
#
# Hard rule:
# - Never index facts directly
# - Missing data degrades reasoning, not crashes it
# ==========================================================

def evaluate(facts: dict, baseline: dict) -> list:
    judgments = []

    # -------- CPU --------
    cpu_usage = (
        facts.get("cpu_usage")
        or facts.get("cpu", {}).get("usage_percent")
        or 0.0
    )

    # -------- MEMORY --------
    memory_used = (
        facts.get("memory_used_mb")
        or facts.get("memory", {}).get("used_mb")
        or 0.0
    )

    memory_total = (
        facts.get("memory_total_mb")
        or facts.get("memory", {}).get("total_mb")
        or 0.0
    )

    # -------- DISK --------
    disk_used = (
        facts.get("disk_used_percent")
        or facts.get("disk", {}).get("used_percent")
        or 0.0
    )

    # -------- EXAMPLE JUDGMENT LOGIC --------
    # (Keep this minimal — you already have real logic)

    if cpu_usage > 85:
        judgments.append({
            "type": "cpu_pressure",
            "severity": "high",
            "value": cpu_usage
        })

    if memory_total > 0:
        mem_ratio = memory_used / memory_total
        if mem_ratio > 0.9:
            judgments.append({
                "type": "memory_pressure",
                "severity": "high",
                "value": mem_ratio
            })

    if disk_used > 90:
        judgments.append({
            "type": "disk_pressure",
            "severity": "high",
            "value": disk_used
        })

    return judgments
