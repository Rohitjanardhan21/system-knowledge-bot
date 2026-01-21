def generate_observations(trends, baselines):
    """
    trends: dict like {'memory': (dir, conf), 'disk': (dir, conf)}
    baselines: dict like {'memory': status, 'disk': status}

    Returns list of observation strings.
    """

    observations = []

    mem_dir, mem_conf = trends.get("memory", ("stable", "weak"))
    mem_base = baselines.get("memory", "normal")

    if mem_dir == "down" and mem_conf in ("moderate", "strong") and mem_base != "normal":
        observations.append(
            "Available memory has been consistently lower than usual."
        )

    disk_dir, disk_conf = trends.get("disk", ("stable", "weak"))
    disk_base = baselines.get("disk", "normal")

    if disk_dir == "up" and disk_conf in ("moderate", "strong") and disk_base != "normal":
        observations.append(
            "Disk usage has been steadily increasing beyond its usual range."
        )

    return observations
