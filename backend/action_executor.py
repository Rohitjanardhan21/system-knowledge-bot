import time
import os
import psutil
from datetime import datetime

from backend.timeline_engine import log_event
from backend.experience_store import store_experience
from backend.safety_guard import is_safe
from backend.dqn_agent import DQNAgent
from backend.simulation_engine import SimulationEngine
from backend.causal_engine import CausalEngine
from backend.self_optimizer import update_optimizer, get_optimizer

# 🔥 NEW
from backend.action_history import record as record_action
from backend.action_feedback import penalize, is_blocked

COOLDOWN_SECONDS = 2
GLOBAL_COOLDOWN = 5

SAFE_PROCESSES = ["systemd", "init", "python", "bash"]


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

    # -----------------------------------------
    # COOLDOWN
    # -----------------------------------------
    def can_execute(self, action, decision):

        # 🔥 block bad actions
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

    # -----------------------------------------
    # METRICS
    # -----------------------------------------
    def get_metrics(self):
        return {
            "cpu": psutil.cpu_percent(interval=0.5),
            "memory": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage('/').percent,
        }

    # -----------------------------------------
    # MAIN EXECUTION
    # -----------------------------------------
    def execute(self, decision):

        action = decision.get("action")
        context = decision.get("context", "general")
        baseline = decision.get("baseline_cpu", 50)

        if not action:
            return {"status": "no_action"}

        if not is_safe(action):
            return {"status": "blocked_by_safety", "action": action}

        if not self.can_execute(action, decision):
            return {"status": "cooldown_or_blocked", "action": action}

        # ---------------- BEFORE ----------------
        before = self.get_metrics()

        # 🔥 BASELINE FILTER (ignore normal usage)
        if before["cpu"] < baseline + 20:
            return {"status": "ignored_normal_usage"}

        # 🔥 CONTEXT FILTER
        if context == "gaming":
            return {"status": "ignored_gaming_context"}

        state = self.agent.encode_state(before)

        # ---------------- CAUSAL ----------------
        causal = CausalEngine().detect(
            {
                "cpu_pct": before["cpu"],
                "mem_pct": before["memory"],
                "disk_pct": before["disk"]
            },
            {
                "cpu": {"pattern": "unknown"},
                "memory": {"pattern": "unknown"},
                "disk": {"pattern": "unknown"}
            }
        )

        risk = causal.get("system_risk", 0)

        # ---------------- SIMULATION ----------------
        simulated = self.simulator.apply_action(before, action)
        sim_score = self.simulator.evaluate_state(simulated)

        opt = get_optimizer()
        reward_scale = opt.get("reward_scale", 1.0) or 1.0
        block_threshold = -200 * reward_scale

        if self.agent.epsilon < 0.7:
            if sim_score < block_threshold and risk < 0.3:
                return {
                    "status": "blocked_by_simulation",
                    "reason": "Predicted negative outcome",
                    "simulated": simulated
                }

        # ---------------- EXECUTION ----------------
        result = self._execute_action(action, decision)

        time.sleep(1)

        # ---------------- AFTER ----------------
        after = self.get_metrics()

        # ---------------- REWARD ----------------
        reward = self._compute_reward(before, after, action, result)

        next_state = self.agent.encode_state(after)

        if result.get("status") == "executed":
            self.agent.remember(state, action, reward, next_state)
            self.agent.train()

            store_experience(state.tolist(), action, reward, before, after)
            update_optimizer("balanced", reward)

            record_action(action, reward)

            # 🔥 SELF-CORRECTION
            if reward < 0:
                penalize(action)

        # ---------------- EXPLANATION ----------------
        explanation = self._build_explanation(action, before, after, causal)

        # ---------------- LOG ----------------
        log_event({
            "time": datetime.utcnow().isoformat(),
            "event": f"Executed: {action}",
            "reward": reward,
            "risk": risk
        })

        result.update({
            "reward": reward,
            "risk": risk,
            "before": before,
            "after": after,
            "explanation": explanation
        })

        return result

    # -----------------------------------------
    # REWARD FUNCTION
    # -----------------------------------------
    def _compute_reward(self, before, after, action, result):

        if result.get("status") != "executed":
            return -0.5

        cpu_gain = before["cpu"] - after["cpu"]
        mem_gain = before["memory"] - after["memory"]
        disk_gain = before["disk"] - after["disk"]

        reward = (
            cpu_gain * 1.5 +
            mem_gain * 1.0 +
            disk_gain * 0.5
        )

        if reward < 0:
            reward -= 1

        return round(reward, 3)

    # -----------------------------------------
    # EXPLANATION
    # -----------------------------------------
    def _build_explanation(self, action, before, after, causal):

        return {
            "action": action,
            "cause": causal.get("primary_cause", {}).get("type"),
            "cpu_before": before["cpu"],
            "cpu_after": after["cpu"],
            "improvement": round(before["cpu"] - after["cpu"], 2),
            "result": "improved" if after["cpu"] < before["cpu"] else "no_effect"
        }

    # -----------------------------------------
    # ACTION HANDLER
    # -----------------------------------------
    def _execute_action(self, action, decision):

        if action == "kill_process":
            return self.kill_specific_process(decision)

        if action == "throttle_process":
            return self.throttle_specific_process(decision)

        if action == "kill_high_cpu_process":
            return self.kill_high_cpu()

        return {"status": "executed", "action": action}

    # -----------------------------------------
    # SAFE PROCESS KILL (WINDOWS SAFE)
    # -----------------------------------------
    def kill_specific_process(self, decision):

        pid = decision.get("target_pid")
        name = (decision.get("target_name") or "").lower()

        if not pid:
            return {"status": "error", "message": "missing pid"}

        if pid < 100:
            return {"status": "blocked", "reason": "system pid"}

        if name in SAFE_PROCESSES:
            return {"status": "blocked", "reason": "protected process"}

        try:
            # 🔥 cross-platform safe kill
            proc = psutil.Process(pid)
            proc.terminate()
            return {"status": "executed", "action": "kill_process", "pid": pid}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    # -----------------------------------------
    def throttle_specific_process(self, decision):
        return {"status": "executed", "action": "throttle_process"}

    # -----------------------------------------
    def kill_high_cpu(self):
        return {"status": "executed", "action": "kill_high_cpu_process"}
