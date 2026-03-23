import json
from pathlib import Path
from datetime import datetime, timedelta

ALERT_FILE = Path("system_facts/alerts/active.json")
ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)

TTL_MINUTES = 30


# ---------------------------------------------------------
# Load Alerts (SAFE)
# ---------------------------------------------------------
def load_alerts():
    # 🔥 Ensure file exists
    if not ALERT_FILE.exists():
        ALERT_FILE.write_text("[]")
        return []

    try:
        content = ALERT_FILE.read_text().strip()

        # 🔥 Handle empty file
        if not content:
            return []

        return json.loads(content)

    except Exception:
        # 🔥 If corrupted → reset file
        ALERT_FILE.write_text("[]")
        return []


# ---------------------------------------------------------
# Save Alerts
# ---------------------------------------------------------
def save_alerts(alerts):
    ALERT_FILE.write_text(json.dumps(alerts, indent=2))


# ---------------------------------------------------------
# Remove expired alerts
# ---------------------------------------------------------
def purge_expired(alerts):
    now = datetime.utcnow()
    active = []

    for a in alerts:
        try:
            ts = datetime.fromisoformat(a["first_seen"])
            if now - ts < timedelta(minutes=TTL_MINUTES):
                active.append(a)
        except Exception:
            continue

    return active


# ---------------------------------------------------------
# Register Alerts
# ---------------------------------------------------------
def register_alerts(anomalies):
    alerts = purge_expired(load_alerts())
    now = datetime.utcnow().isoformat()

    for anomaly in anomalies:
        key = f"{anomaly['type']}:{anomaly.get('metric')}"

        existing = next((a for a in alerts if a["key"] == key), None)

        if existing:
            existing["last_seen"] = now
            existing["count"] += 1

            # 🔥 Safe severity comparison
            severity_order = ["low", "medium", "high"]
            existing["severity"] = max(
                existing["severity"],
                anomaly["severity"],
                key=lambda s: severity_order.index(s) if s in severity_order else 0
            )

        else:
            alerts.append({
                "key": key,
                "type": anomaly["type"],
                "metric": anomaly.get("metric"),
                "severity": anomaly.get("severity", "low"),
                "confidence": anomaly.get("confidence", 0.5),
                "first_seen": now,
                "last_seen": now,
                "count": 1,
            })

    save_alerts(alerts)
    return alerts
