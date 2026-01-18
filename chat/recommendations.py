def recommend(memory, disk):
    if memory["available_mb"] / memory["total_mb"] < 0.2:
        return "If you change one thing, increasing RAM would give the biggest improvement."

    for fs in disk["filesystems"]:
        if fs["mount_point"] == "/" and fs["used_gb"] / fs["size_gb"] > 0.8:
            return "Freeing disk space would improve system stability."

    return None
