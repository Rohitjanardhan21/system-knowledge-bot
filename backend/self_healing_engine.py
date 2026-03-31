import os
import signal
from datetime import datetime
from pathlib import Path
import json
import uuid
import platform

LOG_FILE = Path("system_facts/actions_log.json")
PENDING_FILE = Path("system_facts/pending_actions.json")

LOG_FILE.parent.mkdir(exist_ok=True)


class SelfHealingEngine:

    def __init__(self):
        self.safe_mode = True  # 🔥 ALWAYS default ON
        self.os_type = platform.system().lower()

        # ❌ NEVER TOUCH THESE
        self.protected_processes = [
            "systemd", "init", "gnome", "explorer",
            "kernel", "idle", "winlogon", "csrss"
        ]

    # ---------------------------------------------------------
    # 🔍 SAFETY CHECK
    # ---------------------------------------------------------
    def is_safe(self, process_name):
        name = (process_name or "").lower()
        return not any(p in name for p in self.protected_processes)

    # ---------------------------------------------------------
    # 🧠 DECIDE (PROPOSE ONLY — NO EXECUTION)
    # ---------------------------------------------------------
    def decide(self, root, recommendation, prediction):

        if not root:
            return None

        recommendation = recommendation or {}
        prediction = prediction or {}

        cpu = root.get("cpu", 0)
        name = root.get("process")

        # 🚨 CRITICAL CONDITION
        if prediction.get("title") == "overload":
            return self._build_action(name, 0.9, "high")

        # 🔥 HIGH CPU + HIGH PRIORITY
        if cpu > 85 and recommendation.get("priority") in ["HIGH", "CRITICAL"]:
            return self._build_action(name, 0.8, "medium")

        return None

    # ---------------------------------------------------------
    # 🧩 ACTION BUILDER
    # ---------------------------------------------------------
    def _build_action(self, process_name, confidence, risk):

        if not process_name:
            return None

        if not self.is_safe(process_name):
            return {
                "status": "blocked",
                "reason": "Protected process"
            }

        return {
            "id": str(uuid.uuid4()),
            "type": "kill_process",
            "target": process_name,
            "confidence": confidence,
            "risk": risk,
            "requires_approval": True,
            "message": f"Suggested termination of {process_name}",
            "human_note": "⚠️ Requires human approval before execution."
        }

    # ---------------------------------------------------------
    # 📥 STORE PENDING ACTION
    # ---------------------------------------------------------
    def store_pending(self, action):

        if not action or action.get("status") == "blocked":
            return None

        data = []

        if PENDING_FILE.exists():
            try:
                data = json.loads(PENDING_FILE.read_text())
            except Exception:
                data = []

        data.append(action)

        PENDING_FILE.write_text(json.dumps(data[-50:], indent=2))

        return action

    # ---------------------------------------------------------
    # ⚡ EXECUTE (ONLY AFTER APPROVAL)
    # ---------------------------------------------------------
    def execute(self, action):

        if not action:
            return None

        action_type = action.get("type")
        target = action.get("target")

        # SAFETY CHECK AGAIN
        if not self.is_safe(target):
            return {
                "status": "blocked",
                "reason": "Protected process"
            }

        # 🔥 SAFE MODE (DEFAULT)
        if self.safe_mode:
            return {
                "status": "simulation",
                "message": f"[SAFE MODE] Would terminate {target}"
            }

        try:
            if self.os_type == "linux":
                os.system(f"pkill -f {target}")

            elif self.os_type == "windows":
                os.system(f"taskkill /F /IM {target}.exe")

            result = {
                "status": "executed",
                "message": f"Terminated {target}"
            }

        except Exception as e:
            result = {
                "status": "failed",
                "error": str(e)
            }

        self.log_action(action, result)
        return result

    # ---------------------------------------------------------
    # 📝 LOGGING (AUDIT SAFE)
    # ---------------------------------------------------------
    def log_action(self, action, result):

        log = []

        if LOG_FILE.exists():
            try:
                log = json.loads(LOG_FILE.read_text())
            except Exception:
                log = []

        log.append({
            "time": datetime.utcnow().isoformat(),
            "action": action,
            "result": result
        })

        LOG_FILE.write_text(json.dumps(log[-200:], indent=2))
