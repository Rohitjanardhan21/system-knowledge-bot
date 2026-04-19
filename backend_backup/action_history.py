# backend/action_history.py

import json
import os
from datetime import datetime

HISTORY_PATH = "system_facts/action_history.json"
os.makedirs("system_facts", exist_ok=True)


class ActionHistory:

    def __init__(self):
        self.history = []
        self._load()

    # -----------------------------------------
    def _load(self):
        if os.path.exists(HISTORY_PATH):
            try:
                with open(HISTORY_PATH, "r") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []

    def _save(self):
        with open(HISTORY_PATH, "w") as f:
            json.dump(self.history[-200:], f, indent=2)

    # -----------------------------------------
    def log_action(self, action, reward=None, meta=None):
        entry = {
            "time": datetime.utcnow().isoformat(),
            "action": action,
            "reward": reward,
            "meta": meta or {}
        }

        self.history.append(entry)
        self._save()

    # -----------------------------------------
    def load_history(self, limit=50):
        return self.history[-limit:]


# =========================================================
# 🔥 GLOBAL INSTANCE + FUNCTIONS (FIX IMPORT ERROR)
# =========================================================

_history_engine = ActionHistory()


def log_action(action, reward=None, meta=None):
    _history_engine.log_action(action, reward, meta)


def load_history(limit=50):
    return _history_engine.load_history(limit)
# ---------------------------------------------------------
# 🔥 BACKWARD COMPATIBILITY (FIX IMPORT ERROR)
# ---------------------------------------------------------

def record(action, reward=None, meta=None):
    log_action(action, reward, meta)
