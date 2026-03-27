# backend/replay_buffer.py

import random
from collections import deque


class ReplayBuffer:
    def __init__(self, capacity=5000):
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state):
        self.buffer.append((state, action, reward, next_state))

    def sample(self, batch_size=32):
        return random.sample(self.buffer, batch_size)

    def __len__(self):
        return len(self.buffer)
