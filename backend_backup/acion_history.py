import json
from pathlib import Path
from datetime import datetime

HISTORY_FILE = Path("system_facts/action_history.json")
HISTORY_FILE.parent.mkdir(exist_ok=True)

def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []

def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history, indent=2))

def log_action(action, result):
    history = load_history()

    entry = {
        "time": datetime.now().isoformat(),
        "action": action,
        "result": result,
        "undo": get_undo_action(action)
    }

    history.append(entry)
    save_history(history)

def get_undo_action(action):
    if action["type"] == "kill_process":
        return {"type": "restart_process", "target": action["target_name"]}
    return None
