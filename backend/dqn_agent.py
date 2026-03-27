import torch
import torch.nn as nn
import random
import numpy as np

from backend.memory_engine import get_system_profile
from backend.self_optimizer import get_optimizer


# -------------------------------------------------
# 🔥 GLOBAL ACTION SPACE
# -------------------------------------------------
ACTIONS = [
    "throttle_background_processes",
    "free_memory_cache",
    "preemptive_cpu_control",
    "kill_high_cpu_process",
    "maintain_state"
]


# -------------------------------------------------
# 🧠 MODEL
# -------------------------------------------------
class DQN(nn.Module):
    def __init__(self, state_dim, action_dim, hidden):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, action_dim)
        )

    def forward(self, x):
        return self.net(x)


# -------------------------------------------------
# 🤖 AGENT
# -------------------------------------------------
class DQNAgent:

    def __init__(self):

        profile = get_system_profile()
        ram = profile.get("memory", {}).get("total_gb", 8)

        hidden = 64 if ram > 16 else 32

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.state_dim = 6
        self.action_dim = len(ACTIONS)

        self.model = DQN(self.state_dim, self.action_dim, hidden).to(self.device)
        self.target_model = DQN(self.state_dim, self.action_dim, hidden).to(self.device)

        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)

        self.buffer = []
        self.buffer_limit = 5000

        self.gamma = 0.95

        opt = get_optimizer()
        self.epsilon = opt.get("epsilon", 1.0)

        self.epsilon_min = 0.05
        self.epsilon_decay = 0.995

        self.step_count = 0

    # -------------------------------------------------
    # 🧠 STATE ENCODING (SAFE)
    # -------------------------------------------------
    def encode_state(self, m):

        if not isinstance(m, dict):
            return np.array(m, dtype=np.float32)

        return np.array([
            m.get("cpu", 0) / 100,
            m.get("memory", 0) / 100,
            m.get("disk", 0) / 100,
            m.get("network", {}).get("latency", 0) / 100,
            m.get("network", {}).get("throughput", 0) / 100,
            len(m.get("processes", [])) / 100
        ], dtype=np.float32)

    # -------------------------------------------------
    # 🔥 FIXED ACTION SELECTION
    # -------------------------------------------------
    def select_action(self, state, available_actions=None):

        # -----------------------------------------
        # FILTER ACTION SPACE
        # -----------------------------------------
        if available_actions:
            valid_actions = [a for a in available_actions if a in ACTIONS]
            if not valid_actions:
                valid_actions = ACTIONS
        else:
            valid_actions = ACTIONS

        # -----------------------------------------
        # EPSILON-GREEDY
        # -----------------------------------------
        if random.random() < self.epsilon:
            return random.choice(valid_actions)

        # -----------------------------------------
        # 🔥 FIX: ENCODE STATE BEFORE MODEL
        # -----------------------------------------
        state_vec = self.encode_state(state)

        state_t = torch.tensor(state_vec, dtype=torch.float32).unsqueeze(0).to(self.device)
        q_values = self.model(state_t)[0].detach().cpu().numpy()

        # -----------------------------------------
        # MAP VALID ACTIONS ONLY
        # -----------------------------------------
        action_q = {
            action: q_values[ACTIONS.index(action)]
            for action in valid_actions
        }

        return max(action_q, key=action_q.get)

    # -------------------------------------------------
    # 🧠 MEMORY BUFFER
    # -------------------------------------------------
    def remember(self, s, a, r, s2):

        if len(self.buffer) >= self.buffer_limit:
            self.buffer.pop(0)

        self.buffer.append((s, ACTIONS.index(a), r, s2))

    # -------------------------------------------------
    # 🧠 TRAINING (DOUBLE DQN)
    # -------------------------------------------------
    def train(self, batch_size=32):

        if len(self.buffer) < batch_size:
            return

        batch = random.sample(self.buffer, batch_size)

        s, a, r, s2 = zip(*batch)

        s = torch.tensor(s, dtype=torch.float32).to(self.device)
        a = torch.tensor(a).to(self.device)
        r = torch.tensor(r, dtype=torch.float32).to(self.device)
        s2 = torch.tensor(s2, dtype=torch.float32).to(self.device)

        q = self.model(s)
        q_val = q.gather(1, a.unsqueeze(1)).squeeze()

        next_actions = self.model(s2).argmax(1)
        next_q = self.target_model(s2).gather(1, next_actions.unsqueeze(1)).squeeze()

        target = r + self.gamma * next_q

        loss = nn.functional.mse_loss(q_val, target.detach())

        self.optimizer.zero_grad()
        loss.backward()

        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)

        self.optimizer.step()

        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        self.step_count += 1
        if self.step_count % 50 == 0:
            self.target_model.load_state_dict(self.model.state_dict())

    # -------------------------------------------------
    # 🔍 DEBUG
    # -------------------------------------------------
    def debug_q_values(self, state):

        state_vec = self.encode_state(state)

        state_t = torch.tensor(state_vec, dtype=torch.float32).unsqueeze(0).to(self.device)
        q = self.model(state_t).detach().cpu().numpy()[0]

        return {a: float(q[i]) for i, a in enumerate(ACTIONS)}
