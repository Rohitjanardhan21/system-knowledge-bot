# ---------------------------------------------------------
# DIAGNOSIS ENGINE
# ---------------------------------------------------------
# Converts system intelligence into human-readable insights


def generate_diagnosis(state):

    causal = state.get("causal", {})
    processes = state.get("all_processes", [])
    prediction = state.get("prediction")

    # 🔥 NEW CONTEXT + BASELINE
    context = state.get("context", "general")
    baseline = state.get("baseline_cpu", 50)

    primary = causal.get("primary_cause", {}).get("type")
    confidence = causal.get("primary_cause", {}).get("confidence", 0)

    global_state = state.get("global_state", {})
    cpu = global_state.get("cpu", 0)
    memory = global_state.get("memory", 0)
    disk = global_state.get("disk", 0)

    # ---------------------------------------------------------
    # FIND HEAVIEST PROCESS
    # ---------------------------------------------------------
    top_process = None

    if processes:
        try:
            top_process = max(processes, key=lambda p: p.get("cpu", 0))
        except Exception:
            top_process = None

    process_name = (
        top_process.get("name")
        if top_process and top_process.get("name")
        else "a background process"
    )

    process_cpu = top_process.get("cpu", 0) if top_process else 0

    # ---------------------------------------------------------
    # CONTEXT-AWARE HANDLING
    # ---------------------------------------------------------

    # 🎮 GAMING → DO NOT DISTURB
    if context == "gaming":
        return {
            "summary": "High CPU usage detected, but this is expected during gaming.",
            "details": f"{process_name} is using {round(process_cpu,1)}% CPU.",
            "suggestion": "No action needed unless you notice lag or overheating.",
            "confidence": 0.95
        }

    # 💻 DEVELOPMENT → TOLERANT
    if context == "development":
        if cpu < baseline + 20:
            return {
                "summary": "System load is slightly elevated due to development activity.",
                "details": f"{process_name} is active but within your normal usage range.",
                "suggestion": "No action required.",
                "confidence": 0.9
            }

    # ---------------------------------------------------------
    # CPU OVERLOAD
    # ---------------------------------------------------------
    if primary == "cpu_overload":

        abnormal = cpu > baseline + 20

        return {
            "summary": f"{process_name} is causing high CPU usage.",
            "details": (
                f"CPU is at {round(cpu,1)}%, which is "
                f"{'above your normal usage' if abnormal else 'near your usual usage'}."
            ),
            "suggestion": "Close unnecessary apps or reduce workload.",
            "confidence": confidence or 0.85
        }

    # ---------------------------------------------------------
    # MEMORY PRESSURE
    # ---------------------------------------------------------
    if primary == "memory_pressure":

        return {
            "summary": f"High memory usage detected, likely caused by {process_name}.",
            "details": f"Memory is at {round(memory,1)}%, which may slow down your system.",
            "suggestion": "Close unused applications or clear memory.",
            "confidence": confidence or 0.8
        }

    # ---------------------------------------------------------
    # DISK BOTTLENECK
    # ---------------------------------------------------------
    if primary == "disk_io_bottleneck":

        return {
            "summary": "Disk activity is high and may reduce performance.",
            "details": f"Disk usage is at {round(disk,1)}%, indicating heavy I/O operations.",
            "suggestion": "Pause large downloads or disk-heavy tasks.",
            "confidence": confidence or 0.75
        }

    # ---------------------------------------------------------
    # SUSTAINED LOAD
    # ---------------------------------------------------------
    if primary == "sustained_compute_load":

        return {
            "summary": "System is under continuous load.",
            "details": f"{process_name} is consistently using CPU resources.",
            "suggestion": "Consider reducing workload or distributing tasks.",
            "confidence": confidence or 0.7
        }

    # ---------------------------------------------------------
    # PREDICTIVE WARNING
    # ---------------------------------------------------------
    if prediction:

        return {
            "summary": prediction.get("message", "Potential issue detected."),
            "details": "System trends indicate a possible upcoming performance issue.",
            "suggestion": "Monitor usage or take preventive action.",
            "confidence": prediction.get("confidence", 0.7)
        }

    # ---------------------------------------------------------
    # NORMAL STATE
    # ---------------------------------------------------------
    return {
        "summary": "System is running normally.",
        "details": f"CPU ({round(cpu,1)}%), Memory ({round(memory,1)}%), and Disk are within expected limits.",
        "suggestion": "No action needed.",
        "confidence": 0.95
    }
