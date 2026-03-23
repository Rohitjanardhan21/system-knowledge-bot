from pathlib import Path
import json
import uuid
from datetime import datetime

ALERTS_PATH = Path("system_facts/alerts.json")
ALERTS_PATH.parent.mkdir(exist_ok=True)


def _load():
    if ALERTS_PATH.exists():
        return json.loads(ALERTS_PATH.read_text())
    return []


def _save(alerts):
    ALERTS_PATH.write_text(json.dumps(alerts, indent=2))


def create_alert(severity, source, message):

    alerts = _load()

    alert = {
        "id": f"a-{uuid.uuid4().hex[:8]}",
        "severity": severity,
        "source": source,
        "message": message,
        "created_at": datetime.utcnow().isoformat(),
        "acknowledged": False
    }

    alerts.append(alert)
    _save(alerts)

    return alert


def list_alerts(active_only=True):

    alerts = _load()

    if active_only:
        return [a for a in alerts if not a["acknowledged"]]

    return alerts


def ack_alert(alert_id):

    alerts = _load()

    for a in alerts:
        if a["id"] == alert_id:
            a["acknowledged"] = True
            _save(alerts)
            return a

    return None
