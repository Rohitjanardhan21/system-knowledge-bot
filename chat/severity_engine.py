def classify_severity(
    trend_dir, trend_conf,
    baseline_status,
    component
):
    """
    Determines severity for a single component.
    component: 'memory' or 'disk'
    """

    # Default
    severity = "info"
    reason = "Behavior is within expected range."

    # -------- Memory rules --------
    if component == "memory":
        if baseline_status == "unusual" and trend_dir == "down":
            severity = "warning"
            reason = "Available memory is lower than usual and still decreasing."
        elif baseline_status == "elevated":
            severity = "attention"
            reason = "Available memory is lower than usual for this system."

    # -------- Disk rules --------
    if component == "disk":
        if baseline_status == "unusual" and trend_dir == "up":
            severity = "warning"
            reason = "Disk usage is higher than usual and still increasing."
        elif baseline_status == "elevated":
            severity = "attention"
            reason = "Disk usage is higher than usual for this system."

    return severity, reason
