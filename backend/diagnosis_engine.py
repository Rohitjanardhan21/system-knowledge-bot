# ---------------------------------------------------------
# DIAGNOSIS ENGINE (PRODUCTION-GRADE)
# ---------------------------------------------------------
# Converts system intelligence into safe, structured insights


def generate_diagnosis(state):

    causal = state.get("causal", {})
    processes = state.get("all_processes", [])
    prediction = state.get("prediction")

    # 🔥 CONTEXT + BASELINE
    context = state.get("context", "general")
    baseline = state.get("baseline_cpu", 50)

    primary = causal.get("primary_cause", {}).get("type")
    confidence = causal.get("primary_cause", {}).get("confidence", 0.0)

    global_state = state.get("global_state", {})
    cpu = global_state.get("cpu", 0)
    memory = global_state.get("memory", 0)
    disk = global_state.get("disk", 0)

    # ---------------------------------------------------------
    # SAFE CONFIDENCE NORMALIZATION
    # ---------------------------------------------------------
    confidence = max(0.5, min(confidence or 0.8, 0.99))

    # ---------------------------------------------------------
    # FIND HEAVIEST PROCESS (SAFE)
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
    # HELPER FLAGS
    # ---------------------------------------------------------
    abnormal_cpu = cpu > baseline + 20
    high_cpu = cpu > 80
    high_memory = memory > 80
    high_disk = disk > 80

    # ---------------------------------------------------------
    # CONTEXT-AWARE HANDLING
    # ---------------------------------------------------------

    if context == "gaming":
        return {
            "status": "expected_load",
            "summary": "High CPU usage detected, but this is expected during gaming.",
            "details": f"{process_name} is using {round(process_cpu,1)}% CPU.",
            "suggestion": "No action needed unless you notice lag or overheating.",
            "action": None,
            "confidence": 0.95,
            "risk": "LOW"
        }

    if context == "development":
        if cpu < baseline + 20:
            return {
                "status": "normal_dev_load",
                "summary": "System load is slightly elevated due to development activity.",
                "details": f"{process_name} is active but within your normal usage range.",
                "suggestion": "No action required.",
                "action": None,
                "confidence": 0.9,
                "risk": "LOW"
            }

    # ---------------------------------------------------------
    # CPU OVERLOAD
    # ---------------------------------------------------------
    if primary == "cpu_overload" or high_cpu:

        action = {
            "type": "reduce_cpu",
            "target_name": process_name
        }

        return {
            "status": "issue",
            "summary": f"{process_name} is causing high CPU usage.",
            "details": (
                f"CPU is at {round(cpu,1)}%, which is "
                f"{'above your normal usage' if abnormal_cpu else 'near your usual usage'}."
            ),
            "suggestion": "Close unnecessary apps or reduce workload.",
            "action": action,
            "confidence": confidence,
            "risk": "HIGH" if high_cpu else "MEDIUM"
        }

    # ---------------------------------------------------------
    # MEMORY PRESSURE
    # ---------------------------------------------------------
    if primary == "memory_pressure" or high_memory:

        action = {
            "type": "free_memory",
            "target_name": process_name
        }

        return {
            "status": "issue",
            "summary": f"High memory usage detected, likely caused by {process_name}.",
            "details": f"Memory is at {round(memory,1)}%, which may slow down your system.",
            "suggestion": "Close unused applications or clear memory.",
            "action": action,
            "confidence": confidence,
            "risk": "HIGH" if high_memory else "MEDIUM"
        }

    # ---------------------------------------------------------
    # DISK BOTTLENECK
    # ---------------------------------------------------------
    if primary == "disk_io_bottleneck" or high_disk:

        action = {
            "type": "reduce_disk_io",
            "target_name": process_name
        }

        return {
            "status": "issue",
            "summary": "Disk activity is high and may reduce performance.",
            "details": f"Disk usage is at {round(disk,1)}%, indicating heavy I/O operations.",
            "suggestion": "Pause large downloads or disk-heavy tasks.",
            "action": action,
            "confidence": confidence,
            "risk": "MEDIUM"
        }

    # ---------------------------------------------------------
    # SUSTAINED LOAD
    # ---------------------------------------------------------
    if primary == "sustained_compute_load":

        return {
            "status": "load",
            "summary": "System is under continuous load.",
            "details": f"{process_name} is consistently using CPU resources.",
            "suggestion": "Consider reducing workload or distributing tasks.",
            "action": None,
            "confidence": confidence,
            "risk": "MEDIUM"
        }

    # ---------------------------------------------------------
    # PREDICTIVE WARNING
    # ---------------------------------------------------------
    if prediction:

        return {
            "status": "warning",
            "summary": prediction.get("message", "Potential issue detected."),
            "details": "System trends indicate a possible upcoming performance issue.",
            "suggestion": "Monitor usage or take preventive action.",
            "action": None,
            "confidence": prediction.get("confidence", 0.7),
            "risk": "MEDIUM"
        }

    # ---------------------------------------------------------
    # NORMAL STATE
    # ---------------------------------------------------------
    return {
        "status": "healthy",
        "summary": "System is running normally.",
        "details": f"CPU ({round(cpu,1)}%), Memory ({round(memory,1)}%), and Disk are within expected limits.",
        "suggestion": "No action needed.",
        "action": None,
        "confidence": 0.95,
        "risk": "LOW"
    }
