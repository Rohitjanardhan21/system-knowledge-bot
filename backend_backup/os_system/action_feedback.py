# ---------------------------------------------------------
# 🧠 ACTION FEEDBACK ENGINE (ADAPTIVE + SAFE)
# ---------------------------------------------------------

import time
import json
from pathlib import Path

STORE_FILE = Path("system_facts/action_feedback.json")


class ActionFeedback:

    def __init__(self):
        self.bad_actions = {}
        self.load()

    # -----------------------------------------------------
    # 📥 LOAD STATE
    # -----------------------------------------------------
    def load(self):
        if STORE_FILE.exists():
            try:
                self.bad_actions = json.loads(STORE_FILE.read_text())
            except:
                self.bad_actions = {}

    # -----------------------------------------------------
    # 💾 SAVE STATE
    # -----------------------------------------------------
    def save(self):
        STORE_FILE.parent.mkdir(exist_ok=True)
        STORE_FILE.write_text(json.dumps(self.bad_actions, indent=2))

    # -----------------------------------------------------
    # ⚠ PENALIZE ACTION
    # -----------------------------------------------------
    def penalize(self, action, reason="unknown"):

        entry = self.bad_actions.get(action, {
            "count": 0,
            "last": 0,
            "reasons": []
        })

        entry["count"] += 1
        entry["last"] = time.time()
        entry["reasons"].append(reason)

        self.bad_actions[action] = entry
        self.save()

    # -----------------------------------------------------
    # 🔄 DECAY (FORGIVE OVER TIME)
    # -----------------------------------------------------
    def decay(self):

        now = time.time()

        for action, data in list(self.bad_actions.items()):
            if now - data["last"] > 60:  # 1 min decay
                data["count"] = max(0, data["count"] - 1)

            if data["count"] == 0:
                del self.bad_actions[action]

        self.save()

    # -----------------------------------------------------
    # 🚫 BLOCK CHECK
    # -----------------------------------------------------
    def is_blocked(self, action):

        self.decay()

        data = self.bad_actions.get(action)

        if not data:
            return False

        return data["count"] > 5

    # -----------------------------------------------------
    # 📊 INSPECT
    # -----------------------------------------------------
    def get_status(self):
        return self.bad_actions


# ---------------------------------------------------------
# GLOBAL INSTANCE (FOR EASY IMPORT)
# ---------------------------------------------------------

feedback_engine = ActionFeedback()


def penalize(action, reason="unknown"):
    feedback_engine.penalize(action, reason)


def is_blocked(action):
    return feedback_engine.is_blocked(action)
