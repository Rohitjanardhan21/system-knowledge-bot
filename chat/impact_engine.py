def assess_impact(component, severity):
    """
    Returns a list of impact statements.
    This does NOT recommend actions — only explains effects.
    """

    impacts = []

    if component == "memory":
        if severity == "warning":
            impacts.append(
                "Improving memory availability would significantly improve performance and responsiveness."
            )
            impacts.append(
                "Without addressing memory pressure, multitasking performance may remain inconsistent."
            )

        elif severity == "attention":
            impacts.append(
                "Memory pressure may occasionally affect performance under load."
            )

    if component == "disk":
        if severity == "warning":
            impacts.append(
                "Reducing disk usage would improve system stability and reduce the risk of write failures."
            )
            impacts.append(
                "Disk cleanup alone is unlikely to improve performance unless memory pressure is also present."
            )

        elif severity == "attention":
            impacts.append(
                "Disk usage is elevated but not yet limiting performance."
            )

    return impacts
