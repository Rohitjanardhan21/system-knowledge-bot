import os
import json
import uuid
import platform
import subprocess
from datetime import datetime
from pathlib import Path


LOG_FILE = Path("system_facts/actions_log.json")
PENDING_FILE = Path("system_facts/pending_actions.json")

LOG_FILE.parent.mkdir(exist_ok=True)


class SelfHealingEngine:

    def __init__(self):
        self.safe_mode = True
        self.os_type = platform.system().lower()

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
    # 🧠 DECISION ENGINE
    # ---------------------------------------------------------
    def decide(self, state):

        root = state.get("root_cause")
        diagnosis = state.get("diagnosis", {})
        anomaly = state.get("anomaly_score", 0)

        if not root:
            return None

        # 🔥 CRITICAL FAILURE
        if diagnosis.get("severity") == "CRITICAL":
            return self._build_action(root, 0.95, "high", auto=True)

        # 🔥 HIGH ANOMALY
        if anomaly > 2.5:
            return self._build_action(root, 0.85, "medium", auto=False)

        return None

    # ---------------------------------------------------------
    def _build_action(self, process_name, confidence, risk, auto=False):

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
            "auto": auto,
            "requires_approval": not auto,
            "priority": "HIGH" if auto else "MEDIUM",
            "message": f"Suggested termination of {process_name}"
        }

    # ---------------------------------------------------------
    # 📥 STORE
    # ---------------------------------------------------------
    def store_pending(self, action):

        if not action or action.get("status") == "blocked":
            return None

        data = []

        if PENDING_FILE.exists():
            try:
                data = json.loads(PENDING_FILE.read_text())
            except:
                data = []

        data.append(action)
        PENDING_FILE.write_text(json.dumps(data[-50:], indent=2))

        return action

    # ---------------------------------------------------------
    # ⚡ SAFE EXECUTION
    # ---------------------------------------------------------
    def execute(self, action):

        if not action:
            return None

        target = action.get("target")

        if not self.is_safe(target):
            return {"status": "blocked", "reason": "Protected"}

        # 🔥 SAFE MODE (DEFAULT)
        if self.safe_mode:
            return {
                "status": "simulation",
                "message": f"[SAFE MODE] Would terminate {target}"
            }

        try:
            if self.os_type == "linux":
                subprocess.run(
                    ["pkill", "-f", target],
                    timeout=2,
                    check=False
                )

            elif self.os_type == "windows":
                subprocess.run(
                    ["taskkill", "/F", "/IM", f"{target}.exe"],
                    timeout=2,
                    check=False
                )

            result = {
                "status": "executed",
                "message": f"Terminated {target}"
            }

        except subprocess.TimeoutExpired:
            result = {
                "status": "failed",
                "error": "Execution timeout"
            }

        except Exception as e:
            result = {
                "status": "failed",
                "error": str(e)
            }

        self.log_action(action, result)
        return result

    # ---------------------------------------------------------
    # 🔁 FEEDBACK LOOP
    # ---------------------------------------------------------
    def feedback(self, action, result):

        return {
            "action_id": action.get("id"),
            "success": result.get("status") == "executed",
            "timestamp": datetime.utcnow().isoformat()
        }

    # ---------------------------------------------------------
    # 📝 LOGGING
    # ---------------------------------------------------------
    def log_action(self, action, result):

        log = []

        if LOG_FILE.exists():
            try:
                log = json.loads(LOG_FILE.read_text())
            except:
                log = []

        log.append({
            "time": datetime.utcnow().isoformat(),
            "action": action,
            "result": result
        })

        LOG_FILE.write_text(json.dumps(log[-200:], indent=2))


# ---------------------------------------------------------
# 🔥 WRAPPER FOR MULTI_AGENT_SYSTEM COMPATIBILITY
# ---------------------------------------------------------

_engine = SelfHealingEngine()

def execute_action(action_name, state):
    """
    Wrapper so your existing system still works
    """

    fake_action = {
        "type": "kill_process",
        "target": state.get("root_cause"),
        "auto": True
    }

    return _engine.execute(fake_action)
