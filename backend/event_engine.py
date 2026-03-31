"""
event_engine.py

Transforms system metrics + intelligence into structured events
that drive UI, alerts, and reasoning layers.

Core responsibilities:
- Detect anomalies
- Generate semantic events
- Assign severity + priority
- Avoid duplicate spam
- Provide narrative-ready output
"""

from datetime import datetime
from collections import deque

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

MAX_HISTORY = 50
ANOMALY_THRESHOLD = 15  # deviation from baseline (%)

# In-memory history (replace with Redis/DB in production)
cpu_history = deque(maxlen=MAX_HISTORY)

# Track last emitted events to avoid duplicates
last_events = {}

# ─────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────

def now():
    return datetime.utcnow().strftime("%H:%M:%S")


def calculate_baseline():
    if not cpu_history:
        return 50
    return sum(cpu_history) / len(cpu_history)


def detect_anomaly(cpu):
    baseline = calculate_baseline()
    deviation = cpu - baseline

    if abs(deviation) > ANOMALY_THRESHOLD:
        return True, baseline, deviation

    return False, baseline, deviation


def classify_severity(cpu):
    if cpu > 85:
        return "critical"
    elif cpu > 70:
        return "high"
    elif cpu > 50:
        return "medium"
    return "low"


def deduplicate(event_key, cooldown=5):
    """
    Prevent same event spamming within cooldown window
    """
    current_time = datetime.utcnow().timestamp()

    if event_key in last_events:
        if current_time - last_events[event_key] < cooldown:
            return True

    last_events[event_key] = current_time
    return False


# ─────────────────────────────────────────────
# CORE EVENT GENERATOR
# ─────────────────────────────────────────────

def generate_events(metrics, intelligence=None):
    """
    Main entry point

    Args:
        metrics: dict (cpu, memory, etc.)
        intelligence: output from multi_agent_system (optional)

    Returns:
        list of structured events
    """

    events = []

    cpu = metrics.get("cpu", 0)
    memory = metrics.get("memory", 0)
    process = metrics.get("root_cause", {}).get("process", "unknown")

    # Update history
    cpu_history.append(cpu)

    # ─────────────────────────────────────────
    # 1. CPU ANOMALY EVENT
    # ─────────────────────────────────────────
    anomaly, baseline, deviation = detect_anomaly(cpu)

    if anomaly and not deduplicate("cpu_anomaly"):
        events.append({
            "type": "anomaly",
            "title": "CPU anomaly detected",
            "message": f"CPU deviated by {round(deviation, 2)}% from baseline ({round(baseline,2)}%)",
            "severity": classify_severity(cpu),
            "timestamp": now(),
            "meta": {
                "cpu": cpu,
                "baseline": baseline,
                "deviation": deviation
            }
        })

    # ─────────────────────────────────────────
    # 2. HIGH LOAD EVENT
    # ─────────────────────────────────────────
    if cpu > 75 and not deduplicate("high_cpu"):
        events.append({
            "type": "resource",
            "title": "High compute load",
            "message": f"CPU usage is at {cpu}% driven by {process}",
            "severity": classify_severity(cpu),
            "timestamp": now(),
            "meta": {
                "process": process
            }
        })

    # ─────────────────────────────────────────
    # 3. MEMORY PRESSURE EVENT
    # ─────────────────────────────────────────
    if memory > 80 and not deduplicate("memory_pressure"):
        events.append({
            "type": "resource",
            "title": "Memory pressure detected",
            "message": f"Memory usage reached {memory}%",
            "severity": "high",
            "timestamp": now(),
            "meta": {
                "memory": memory
            }
        })

    # ─────────────────────────────────────────
    # 4. STABILITY EVENT (FROM INTELLIGENCE)
    # ─────────────────────────────────────────
    if intelligence:
        stability = intelligence.get("semantic", {}).get("state", "")

        if stability == "overloaded" and not deduplicate("system_overload"):
            events.append({
                "type": "system",
                "title": "System overloaded",
                "message": "System entered overloaded state based on semantic analysis",
                "severity": "critical",
                "timestamp": now()
            })

    # ─────────────────────────────────────────
    # 5. RECOVERY EVENT
    # ─────────────────────────────────────────
    if cpu < 50 and not deduplicate("recovery", cooldown=10):
        events.append({
            "type": "recovery",
            "title": "System stabilized",
            "message": "System load returned to normal levels",
            "severity": "low",
            "timestamp": now()
        })

    # ─────────────────────────────────────────
    # 6. DECISION EVENT (IF AVAILABLE)
    # ─────────────────────────────────────────
    if intelligence and "decision" in intelligence:
        decision = intelligence["decision"]

        if decision["action"] != "no_action" and not deduplicate("decision"):
            events.append({
                "type": "decision",
                "title": "Recommended action generated",
                "message": f"{decision['action']} suggested due to {decision['reason']}",
                "severity": "medium",
                "timestamp": now(),
                "meta": {
                    "confidence": decision.get("confidence", 0)
                }
            })

    # ─────────────────────────────────────────
    # SORT EVENTS BY SEVERITY
    # ─────────────────────────────────────────
    severity_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}

    events.sort(key=lambda e: severity_order.get(e["severity"], 0), reverse=True)

    return events
