def assess_capabilities(cpu, memory, storage):
    """
    Returns a list of capability assessments.
    """

    capabilities = []

    cores = cpu.get("logical_cores", 1)
    ram = memory.get("total_mb", 0)
    disk = storage["filesystems"][0]["size_gb"]

    # ---- Development ----
    capabilities.append(
        "This system is well-suited for general development work."
    )

    # ---- Docker / DevOps ----
    if ram >= 8000:
        capabilities.append(
            "This system can comfortably run Docker containers and DevOps tooling."
        )
    else:
        capabilities.append(
            "This system can run Docker and DevOps tools, but limited RAM may restrict running many containers simultaneously."
        )

    # ---- Kubernetes ----
    if ram >= 16000 and cores >= 6:
        capabilities.append(
            "This system is suitable for local Kubernetes clusters with multiple services."
        )
    else:
        capabilities.append(
            "This system can be used for Kubernetes learning and single-node experiments, but is not ideal for heavier cluster simulations."
        )

    # ---- ML / Data ----
    if ram >= 16000:
        capabilities.append(
            "This system can handle small to moderate data science and machine learning workloads."
        )
    else:
        capabilities.append(
            "This system is suitable for learning ML concepts, but resource limits may constrain larger models or datasets."
        )

    # ---- Multitasking ----
    if ram < 8000:
        capabilities.append(
            "Heavy multitasking may be limited due to available memory."
        )

    return capabilities
