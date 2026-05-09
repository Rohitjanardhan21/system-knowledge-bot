def analyze_degradation(disk_health, battery):
    findings = []

    # Disk
    if disk_health["status"] == "warning":
        findings.append(
            "Disk health indicators suggest potential degradation. "
            "It would be wise to back up important data."
        )
    elif disk_health["status"] == "unknown":
        findings.append(
            "Disk health could not be evaluated due to missing SMART access."
        )

    # Battery
    if "health_pct" in battery:
        if battery["health_pct"] < 80:
            findings.append(
                f"Battery health has degraded to about {battery['health_pct']}%, "
                "which may reduce unplugged usage time."
            )

    if not findings:
        findings.append("No obvious hardware degradation detected.")

    return findings
