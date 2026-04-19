import time
import psutil
from datetime import datetime

from backend.timeline_engine import log_event
from backend.experience_store import store_experience
from backend.safety_guard import is_safe
from backend.dqn_agent import DQNAgent
from backend.simulation_engine import SimulationEngine
from backend.causal_engine import CausalEngine
from backend.self_optimizer import update_optimizer, get_optimizer

from backend.action_history import record as record_action
from backend.action_feedback import penalize, is_blocked
from backend.policy_engine import is_action_allowed


COOLDOWN_SECONDS = 2
GLOBAL_COOLDOWN = 5

SAFE_PROCESSES = [
    "system", "systemd", "init",
    "python", "bash", "services",
    "explorer.exe", "wininit"
]


class ActionExecutor:

    def __init__(self):
        self.last_executed = {}
        self.last_global_action = 0

        self.agent = DQNAgent()

        self.simulator = SimulationEngine({
            "cpu": {"memory": 0.3},
            "memory": {"cpu": 0.2},
            "disk": {"cpu": 0.25}
        })

    # ---------------------------------------------------------
    # 🔒 PROCESS SAFETY FILTER
    # ---------------------------------------------------------
    def is_killable(self, name):
        name = (name or "").lower()

        if not name:
            return False

        if any(x in name for x in ["idle", "system idle"]):
            return False

        if name in SAFE_PROCESSES:
            return False

        return True

    # ---------------------------------------------------------
    # COOLDOWN
    # ---------------------------------------------------------
    def can_execute(self, action, decision):

        if is_blocked(action):
            return False

        now = time.time()

        if now - self.last_global_action < GLOBAL_COOLDOWN:
            return False

        key = f"{action}_{decision.get('target_pid', 'global')}"
        last_time = self.last_executed.get(key, 0)

        if now - last_time > COOLDOWN_SECONDS:
            self.last_executed[key] = now
            self.last_global_action = now
            return True

        return False

    # ---------------------------------------------------------
    # METRICS
    # ---------------------------------------------------------
    def get_metrics(self):
        return {
            "cpu": psutil.cpu_percent(interval=0.5),
            "memory": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage('/').percent,
        }

    # ---------------------------------------------------------
    # 🔥 MAIN EXECUTION
    # ---------------------------------------------------------
    def execute(self, decision):

        action = decision.get("action")
        context = decision.get("context", "general")
        baseline = decision.get("baseline_cpu", 50)
        duration = decision.get("duration_seconds", 0)

        if not action:
            return {"status": "no_action"}

        # ---------------- BEFORE ----------------
        before = self.get_metrics()

        # ---------------- CAUSAL ----------------
        causal = CausalEngine().detect(
            {
                "cpu_pct": before["cpu"],
                "mem_pct": before["memory"],
                "disk_pct": before["disk"]
            },
            {},
        )

        primary = causal.get("primary_cause", {})
        contributors = primary.get("contributors", [])

        target_name = primary.get("process") or decision.get("target_name")

        if not target_name:
            return {"status": "no_valid_target"}

        # ---------------- POLICY ----------------
        allowed, reason = is_action_allowed(
            action,
            context=context,
            target_name=target_name
        )

        if not allowed:
            return {"status": "blocked_policy", "reason": reason}

        # ---------------- SAFETY ----------------
        if not is_safe(action):
            return {"status": "blocked_by_safety"}

        if not self.can_execute(action, decision):
            return {"status": "cooldown_or_blocked"}

        # ---------------- CONTEXT ----------------
        if context == "gaming":
            return {"status": "ignored", "reason": "gaming session"}

        if context == "critical":
            return {"status": "blocked", "reason": "critical workload"}

        # ---------------- BASELINE ----------------
        if before["cpu"] < baseline + 20:
            return {"status": "ignored_normal_usage"}

        if duration < 10:
            return {"status": "ignored_short_spike"}

        # ---------------- STATE ----------------
        state = self.agent.encode_state(before)

        # ---------------- SIMULATION ----------------
        simulated = self.simulator.apply_action(before, action)
        sim_score = self.simulator.evaluate_state(simulated)

        opt = get_optimizer()
        reward_scale = opt.get("reward_scale", 1.0)

        if sim_score < -200 * reward_scale:
            return {
                "status": "blocked_simulation",
                "simulated": simulated
            }

        # ---------------- EXECUTION ----------------
        result = self._execute_action(action, target_name, decision)

        time.sleep(1)

        # ---------------- AFTER ----------------
        after = self.get_metrics()

        # ---------------- REWARD ----------------
        reward = self._compute_reward(before, after, result)

        next_state = self.agent.encode_state(after)

        if result.get("status") == "executed":
            self.agent.remember(state, action, reward, next_state)
            self.agent.train()

            store_experience(state.tolist(), action, reward, before, after)
            update_optimizer("balanced", reward)
            record_action(action, reward)

            if reward < 0:
                penalize(action)

        # ---------------- EXPLANATION ----------------
        explanation = {
            "target": target_name,
            "cpu_before": before["cpu"],
            "cpu_after": after["cpu"],
            "improvement": round(before["cpu"] - after["cpu"], 2),
            "contributors": contributors[:3]
        }

        log_event({
            "time": datetime.utcnow().isoformat(),
            "event": f"Executed {action} on {target_name}",
            "reward": reward
        })

        result.update({
            "reward": reward,
            "before": before,
            "after": after,
            "explanation": explanation
        })

        return result

    # ---------------------------------------------------------
    # ACTION HANDLER
    # ---------------------------------------------------------
    def _execute_action(self, action, target_name, decision):

        if action in ["kill_process", "kill_high_cpu_process"]:
            return self.kill_process_by_name(target_name)

        if action == "throttle_process":
            return {"status": "executed", "action": "throttle"}

        return {"status": "executed", "action": action}

    # ---------------------------------------------------------
    # 🔥 SAFE PROCESS KILL
    # ---------------------------------------------------------
    def kill_process_by_name(self, target_name):

        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = proc.info['name']

                if name != target_name:
                    continue

                if not self.is_killable(name):
                    return {"status": "blocked", "reason": "protected process"}

                proc.terminate()

                return {
                    "status": "executed",
                    "action": "kill_process",
                    "target": name
                }

            except:
                continue

        return {"status": "not_found", "target": target_name}

    # ---------------------------------------------------------
    # REWARD
    # ---------------------------------------------------------
    def _compute_reward(self, before, after, result):

        if result.get("status") != "executed":
            return -0.5

        cpu_gain = before["cpu"] - after["cpu"]
        mem_gain = before["memory"] - after["memory"]

        reward = cpu_gain * 1.5 + mem_gain

        if reward < 0:
            reward -= 1

        return round(reward, 3)
