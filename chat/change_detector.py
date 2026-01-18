def compare_memory(prev, curr):
    delta = curr["available_mb"] - prev["available_mb"]

    if abs(delta) < 100:
        return None

    if delta < 0:
        return f"Available memory decreased by {abs(delta)} MB."
    else:
        return f"Available memory increased by {delta} MB."


def compare_disk(prev, curr):
    prev_used = prev["used_gb"]
    curr_used = curr["used_gb"]
    delta = curr_used - prev_used

    if delta == 0:
        return None

    if delta > 0:
        return f"Disk usage increased by {delta} GB."
    else:
        return f"Disk usage decreased by {abs(delta)} GB."
