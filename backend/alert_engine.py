import json
from pathlib import Path
from datetime import datetime, timedelta

# ---------------------------------------------------------
# FILES
# ---------------------------------------------------------
ALERT_FILE = Path("system_facts/alerts/active.json")
HISTORY_FILE = Path("system_facts/alerts/history.json")

ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)

TTL_MINUTES = 30
COOLDOWN_SECONDS = 10  # 🔥 prevent spam

SEVERITY_ORDER = ["low", "medium", "high", "critical"]


# ---------------------------------------------------------
# LOAD / SAVE
# ---------------------------------------------------------
def load_json(path):
    if not path.exists():
        path.write_text("[]")
        return []

    try:
        content = path.read_text().strip()
        return json.loads(content) if content else []
    except:
        path.write_text("[]")
        return []


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))


def load_alerts():
    return load_json(ALERT_FILE)


def save_alerts(alerts):
    save_json(ALERT_FILE, alerts)


def load_history():
    return load_json(HISTORY_FILE)


def save_history(history):
    save_json(HISTORY_FILE, history)


# ---------------------------------------------------------
# CLEANUP
# ---------------------------------------------------------
def purge_expired(alerts):
    now = datetime.utcnow()
    active = []

    for a in alerts:
        try:
            ts = datetime.fromisoformat(a["last_seen"])

            # 🔥 expire if no recent activity
            if now - ts < timedelta(minutes=TTL_MINUTES):
                active.append(a)
            else:
                archive_alert(a)

        except:
            continue

    return active


# ---------------------------------------------------------
# ARCHIVE (VERY IMPORTANT)
# ---------------------------------------------------------
def archive_alert(alert):
    history = load_history()

    alert["resolved_at"] = datetime.utcnow().isoformat()
    history.append(alert)

    history = history[-200:]  # keep last 200

    save_history(history)


# ---------------------------------------------------------
# SEVERITY LOGIC
# ---------------------------------------------------------
def get_higher_severity(a, b):
    return max(a, b, key=lambda s: SEVERITY_ORDER.index(s) if s in SEVERITY_ORDER else 0)


# ---------------------------------------------------------
# REGISTER ALERTS (CORE ENGINE)
# ---------------------------------------------------------
def register_alerts(anomalies):

    alerts = purge_expired(load_alerts())
    now = datetime.utcnow()

    for anomaly in anomalies:

        key = f"{anomaly['type']}:{anomaly.get('metric')}"

        existing = next((a for a in alerts if a["key"] == key), None)

        if existing:

            # 🔥 COOLDOWN (avoid spam updates)
            last_seen = datetime.fromisoformat(existing["last_seen"])
            if (now - last_seen).total_seconds() < COOLDOWN_SECONDS:
                continue

            existing["last_seen"] = now.isoformat()
            existing["count"] += 1

            # 🔥 severity escalation
            existing["severity"] = get_higher_severity(
                existing["severity"],
                anomaly.get("severity", "low")
            )

            # 🔥 confidence smoothing
            existing["confidence"] = round(
                (existing["confidence"] + anomaly.get("confidence", 0.5)) / 2,
                2
            )

        else:
            alerts.append({
                "key": key,
                "type": anomaly["type"],
                "metric": anomaly.get("metric"),
                "severity": anomaly.get("severity", "low"),
                "confidence": anomaly.get("confidence", 0.5),

                "first_seen": now.isoformat(),
                "last_seen": now.isoformat(),

                "count": 1,
                "status": "active"  # 🔥 NEW
            })

    save_alerts(alerts)
    return alerts


# ---------------------------------------------------------
# GET ACTIVE ALERTS
# ---------------------------------------------------------
def get_active_alerts():
    return load_alerts()


# ---------------------------------------------------------
# GET HISTORY
# ---------------------------------------------------------
def get_alert_history():
    return load_history()
