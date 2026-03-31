# ---------------------------------------------------------
# 🔥 PRIORITY 1: PROCESS ROOT CAUSE (ALWAYS FIRST)
# ---------------------------------------------------------
if process_name:

    if cause_type in ["cpu_overload", "moderate_cpu_load"] or cpu > baseline + 20:
        return {
            "status": "issue",
            "summary": f"{process_name} is causing CPU load.",
            "details": (
                f"{process_name} is using {process_cpu}% CPU on {process_node}. "
                f"Total CPU usage is {cpu}%."
            ),
            "suggestion": "Close or limit this process if not needed.",
            "action": {
                "type": "kill",
                "target_name": process_name
            },
            "confidence": confidence,
            "risk": "HIGH" if cpu > 80 else "MEDIUM"
        }

    if cause_type == "memory_pressure":
        return {
            "status": "issue",
            "summary": f"{process_name} is consuming high memory.",
            "details": f"Memory usage is {memory}%, likely impacted by {process_name}.",
            "suggestion": "Close unused applications.",
            "action": {
                "type": "free_memory",
                "target_name": process_name
            },
            "confidence": confidence,
            "risk": "HIGH"
        }

# ---------------------------------------------------------
# 🔥 PRIORITY 2: SYSTEM METRICS (ONLY IF NO PROCESS ISSUE)
# ---------------------------------------------------------
if not process_name:

    if disk > 85:
        return {
            "status": "issue",
            "summary": "Disk usage is critically high.",
            "details": f"Disk usage is {disk}%.",
            "suggestion": "Reduce disk-heavy operations.",
            "action": {
                "type": "reduce_disk_io"
            },
            "confidence": 0.7,
            "risk": "HIGH"
        }

    if memory > 80:
        return {
            "status": "issue",
            "summary": "Memory usage is high.",
            "details": f"Memory usage is {memory}%.",
            "suggestion": "Close unused applications.",
            "action": {
                "type": "free_memory"
            },
            "confidence": 0.7,
            "risk": "MEDIUM"
        }

# ---------------------------------------------------------
# 🔮 PREDICTION
# ---------------------------------------------------------
if prediction:
    return {
        "status": "warning",
        "summary": prediction.get("message", "Potential issue detected."),
        "details": f"{process_name} may continue affecting performance.",
        "suggestion": "Monitor system usage.",
        "action": None,
        "confidence": prediction.get("confidence", 0.7),
        "risk": "MEDIUM"
    }
    # ---------------------------------------------------------
    # NORMAL
    # ---------------------------------------------------------
    return {
        "status": "healthy",
        "summary": "System is stable.",
        "details": f"{process_name} is active but within normal limits.",
        "suggestion": "No action needed.",
        "action": None,
        "confidence": 0.9,
        "risk": "LOW"
    }
