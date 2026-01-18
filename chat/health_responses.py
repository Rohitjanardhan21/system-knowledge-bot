def summarize_health(mem_status, mem_pct, disk_status, disk_pct, overall):
    lines = []

    if overall == "healthy":
        lines.append("Your system looks healthy overall.")
    elif overall == "warning":
        lines.append("Your system is generally okay, but there are a few things to keep an eye on.")
    else:
        lines.append("Your system is under noticeable stress and may start affecting performance.")

    # Memory explanation
    if mem_status == "normal":
        lines.append(
            f"Memory usage is in a comfortable range, with about {mem_pct:.1f}% available."
        )
    elif mem_status == "high":
        lines.append(
            f"Available memory is getting low ({mem_pct:.1f}% free), which can slow down multitasking."
        )
    else:
        lines.append(
            f"Available memory is critically low ({mem_pct:.1f}% free). "
            "This can cause applications to freeze or be terminated."
        )

    # Disk explanation
    if disk_status == "normal":
        lines.append(
            f"Disk usage is within a safe range ({disk_pct:.1f}% used)."
        )
    elif disk_status == "high":
        lines.append(
            f"Disk usage is fairly high ({disk_pct:.1f}% used). "
            "You may want to clean up unused files."
        )
    else:
        lines.append(
            f"Disk usage is very high ({disk_pct:.1f}% used). "
            "This can cause system and application failures."
        )

    return " ".join(lines)
