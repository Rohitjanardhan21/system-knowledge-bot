# ---------------------------------------------------------
# DECISION ENGINE
# ---------------------------------------------------------

"""
Determines WHAT ACTION should be taken and HOW URGENT it is.

Inputs:
- flat metrics
- forecast
- anomalies
- causal output

Outputs:
- urgency level
- recommended action
- time window
- reasoning
"""

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

CRITICAL_CPU = 90
HIGH_CPU = 75

CRITICAL_MEM = 90
HIGH_MEM = 75

CRITICAL_RISK = 0.85
HIGH_RISK = 0.6


# ---------------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------------

def compute_decision(flat_metrics, forecast, anomalies, causal):

    cpu = flat_metrics.get("cpu_pct", 0)
    mem = flat_metrics.get("mem_pct", 0)
    risk = forecast.get("risk_score", 0)

    cause_type = causal.get("type", "unknown")

    # ---------------------------
    # CRITICAL STATE
    # ---------------------------
    if cpu > CRITICAL_CPU or mem > CRITICAL_MEM or risk > CRITICAL_RISK:
        return {
            "urgency": "critical",
            "action": "immediate_intervention",
            "time_window": "immediate",
            "reason": "System is at critical levels and may degrade or freeze"
        }

    # ---------------------------
    # HIGH RISK
    # ---------------------------
    if cpu > HIGH_CPU or mem > HIGH_MEM or risk > HIGH_RISK:
        return {
            "urgency": "high",
            "action": "reduce_load",
            "time_window": "1-2 minutes",
            "reason": "System approaching unsafe levels"
        }

    # ---------------------------
    # CAUSAL-DRIVEN DECISIONS
    # ---------------------------
    if cause_type == "memory_pressure":
        return {
            "urgency": "high",
            "action": "free_memory",
            "time_window": "1-2 minutes",
            "reason": "Memory pressure likely to increase CPU load and slow system"
        }

    if cause_type == "cpu_overload":
        return {
            "urgency": "medium",
            "action": "limit_cpu_processes",
            "time_window": "2-5 minutes",
            "reason": "High CPU usage detected from heavy processes"
        }

    if cause_type == "disk_io_bottleneck":
        return {
            "urgency": "medium",
            "action": "reduce_disk_io",
            "time_window": "5 minutes",
            "reason": "Disk IO bottleneck affecting performance"
        }

    # ---------------------------
    # ANOMALY BASED
    # ---------------------------
    if anomalies:
        return {
            "urgency": "medium",
            "action": "investigate_anomaly",
            "time_window": "5-10 minutes",
            "reason": "Unusual system behavior detected"
        }

    # ---------------------------
    # NORMAL
    # ---------------------------
    return {
        "urgency": "low",
        "action": "no_action_needed",
        "time_window": "none",
        "reason": "System operating normally"
    }
