def assess_capability(cpu, memory):
    """
    Assess what kinds of workloads this system can realistically handle.
    This is heuristic-based, not aspirational.
    """

    cores = cpu.get("logical_cores", 0)
    ram_mb = memory.get("total_mb", 0)

    # Convert to GB for readability
    ram_gb = ram_mb / 1024

    # --- Capability logic ---
    if ram_gb < 8:
        return (
            "This system is suitable for general development, scripting, "
            "and basic Docker usage. It may struggle with heavier workloads "
            "like large Kubernetes setups or machine learning training."
        )

    if cores >= 8 and ram_gb >= 16:
        return (
            "This system can comfortably handle Docker, Kubernetes labs, "
            "and moderate development or data workloads."
        )

    return (
        "This system can handle development tasks and Docker workloads. "
        "More demanding use cases may require additional RAM or CPU cores."
    )
