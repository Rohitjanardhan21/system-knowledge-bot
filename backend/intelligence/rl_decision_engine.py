import random
import json
import os

Q_TABLE_PATH = "system_facts/q_table.json"

ACTIONS = [
    "throttle_background_processes",
    "free_memory_cache",
    "reduce_disk_io",
    "maintain_state"
]


class RLDecisionEngine:

    def __init__(self):
        self.q_table = self.load_q_table()

    def load_q_table(self):
        if os.path.exists(Q_TABLE_PATH):
            return json.load(open(Q_TABLE_PATH))
        return {}

    def save_q_table(self):
        with open(Q_TABLE_PATH, "w") as f:
            json.dump(self.q_table, f)

    def get_state_key(self, state):
        return f"{int(state['cpu']//10)}-{int(state['memory']//10)}-{int(state['disk']//10)}"

    def choose_action(self, state, epsilon=0.2):
        key = self.get_state_key(state)

        if random.random() < epsilon or key not in self.q_table:
            return random.choice(ACTIONS)

        return max(self.q_table[key], key=self.q_table[key].get)

    def update(self, state, action, reward):
        key = self.get_state_key(state)

        if key not in self.q_table:
            self.q_table[key] = {a: 0 for a in ACTIONS}

        self.q_table[key][action] += 0.1 * (reward - self.q_table[key][action])

        self.save_q_table()
   def compute_reward(before, after):
    return (
        (before["cpu"] - after["cpu"]) +
        (before["memory"] - after["memory"]) +
        (before["disk"] - after["disk"])
    )
