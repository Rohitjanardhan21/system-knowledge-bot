import json
from pathlib import Path
from datetime import datetime

TIMELINE_FILE = Path("system_facts/timeline.json")

if not TIMELINE_FILE.exists():
    TIMELINE_FILE.write_text(json.dumps([]))


def log_event(event):
    data = json.loads(TIMELINE_FILE.read_text())

    data.append({
        "time": datetime.utcnow().isoformat(),
        **event
    })

    TIMELINE_FILE.write_text(json.dumps(data[-200:], indent=2))


def get_timeline():
    return json.loads(TIMELINE_FILE.read_text())
