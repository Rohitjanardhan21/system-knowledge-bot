# backend/policy_engine.py

import json
import os
import random
import time

POLICY_PATH = "system_facts/policy.json"
os.makedirs("system_facts", exist_ok=True)

ACTIONS = [
    "throttle_background_processes",
    "free_memory_cache",
    "preemptive_cpu_control",
    "kill_high_cpu_process",
    "maintain_state"
]

# 🔒 CONTEXT RULES
BLOCKED_IN_CONTEXT = {
    "gaming": ["kill_high_cpu_process", "preemptive_cpu_control"],
    "critical": ["kill_high_cpu_process"]
}

PROTECTED_PROCESSES = ["chrome", "postgres", "nginx"]


class PolicyEngine:
    def __init__(self):
        self.policy = self._load_policy()

        self.alpha_positive = 0.1
        self.alpha_negative = 0.2
        self.epsilon = 0.2

        self.last_action_time = {}
        self.cooldown = 15

    # -----------------------------------------
    def _load_policy(self):
        if os.path.exists(POLICY_PATH):
            try:
                with open(POLICY_PATH, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_policy(self):
        with open(POLICY_PATH, "w") as f:
            json.dump(self.policy, f, indent=2)

    # -----------------------------------------
    def _init_state(self, state):
        if state not in self.policy:
            self.policy[state] = {a: 0.0 for a in ACTIONS}

    # -----------------------------------------
    # 🔒 SAFETY CHECK
    # -----------------------------------------
    def is_action_allowed(self, action, context="general", target_name=None):

        # 🚫 Context block
        if action in BLOCKED_IN_CONTEXT.get(context, []):
            return False, f"Blocked in {context} context"

        # 🚫 Protected process
        if target_name and target_name.lower() in PROTECTED_PROCESSES:
            return False, "Protected process"

        return True, "Allowed"

    # -----------------------------------------
    # 🎯 ACTION SELECTION
    # -----------------------------------------
    def get_best_action(self, state: str, context="general"):
        self._init_state(state)
        now = time.time()

        valid_actions = []

        for action in ACTIONS:
            key = f"{state}:{action}"
            last_time = self.last_action_time.get(key, 0)

            if now - last_time < self.cooldown:
                continue

            allowed, _ = self.is_action_allowed(action, context)

            if allowed:
                valid_actions.append(action)

        if not valid_actions:
            return {
                "action": "maintain_state",
                "reason": "No safe actions available"
            }

        # Exploration
        if random.random() < self.epsilon:
            action = random.choice(valid_actions)
            reason = "Exploration"
        else:
            actions = {a: self.policy[state][a] for a in valid_actions}
            action = max(actions, key=actions.get)
            reason = "Best known action"

        self.last_action_time[f"{state}:{action}"] = now

        return {
            "action": action,
            "reason": reason
        }

    # -----------------------------------------
    # 🔁 LEARNING
    # -----------------------------------------
    def update_policy(self, state: str, action: str, reward: float):
        self._init_state(state)

        current_q = self.policy[state].get(action, 0.0)

        alpha = self.alpha_negative if reward < 0 else self.alpha_positive
        new_q = current_q + alpha * (reward - current_q)

        if reward < -0.3:
            new_q -= 0.1

        self.policy[state][action] = round(new_q * 0.98, 4)

        self._save_policy()

    # -----------------------------------------
    def explain(self, state: str):
        self._init_state(state)

        actions = self.policy[state]
        sorted_actions = sorted(actions.items(), key=lambda x: x[1], reverse=True)

        return {
            "state": state,
            "ranking": sorted_actions[:3]
        }

    # -----------------------------------------
    def get_policy(self):
        return self.policy


# =========================================================
# 🔥 GLOBAL INSTANCE + FUNCTION (THIS FIXES YOUR ERROR)
# =========================================================

_policy_engine = PolicyEngine()

def is_action_allowed(action, context="general", target_name=None):
    return _policy_engine.is_action_allowed(
        action,
        context=context,
        target_name=target_name
    )
