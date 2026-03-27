import json
from pathlib import Path
from datetime import datetime

LOG_FILE = Path("system_facts/logs.json")
LOG_FILE.parent.mkdir(exist_ok=True)


def log(message, level="info"):

    logs = []

    if LOG_FILE.exists():
        logs = json.loads(LOG_FILE.read_text())

    logs.append({
        "time": datetime.utcnow().isoformat(),
        "level": level,
        "message": message
    })

    logs = logs[-200:]

    LOG_FILE.write_text(json.dumps(logs, indent=2))


def get_logs():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return []
