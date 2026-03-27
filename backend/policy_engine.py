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


class PolicyEngine:
    def __init__(self):
        self.policy = self._load_policy()

        # 🔥 Learning params
        self.alpha_positive = 0.1
        self.alpha_negative = 0.2
        self.epsilon = 0.2

        # 🔒 Cooldown per state-action
        self.last_action_time = {}
        self.cooldown = 15  # seconds

    # -----------------------------------------
    # LOAD / SAVE
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
    # INIT STATE
    # -----------------------------------------
    def _init_state(self, state):
        if state not in self.policy:
            self.policy[state] = {a: 0.0 for a in ACTIONS}

    # -----------------------------------------
    # GET BEST ACTION (ε-greedy + cooldown)
    # -----------------------------------------
    def get_best_action(self, state: str):
        self._init_state(state)
        now = time.time()

        # 🔒 Filter actions under cooldown
        valid_actions = []
        for action in ACTIONS:
            key = f"{state}:{action}"
            last_time = self.last_action_time.get(key, 0)

            if now - last_time > self.cooldown:
                valid_actions.append(action)

        if not valid_actions:
            return "maintain_state"

        # 🎲 Exploration vs Exploitation
        if random.random() < self.epsilon:
            action = random.choice(valid_actions)
        else:
            actions = {a: self.policy[state][a] for a in valid_actions}
            action = max(actions, key=actions.get)

        # ⏱ Track execution time
        self.last_action_time[f"{state}:{action}"] = now

        return action

    # -----------------------------------------
    # UPDATE POLICY (Q-learning style)
    # -----------------------------------------
    def update_policy(self, state: str, action: str, reward: float):
        self._init_state(state)

        current_q = self.policy[state].get(action, 0.0)

        # 🔥 Stronger learning for bad outcomes
        alpha = self.alpha_negative if reward < 0 else self.alpha_positive

        new_q = current_q + alpha * (reward - current_q)

        # ❌ Extra penalty for clearly bad actions
        if reward < -0.3:
            new_q -= 0.1

        # 🔁 Confidence decay (prevents overfitting)
        self.policy[state][action] = round(new_q * 0.98, 4)

        self._save_policy()

    # -----------------------------------------
    # DEBUG / API
    # -----------------------------------------
    def get_policy(self):
        return self.policy
