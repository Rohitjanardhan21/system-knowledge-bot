import random
import numpy as np


class PrioritizedReplayBuffer:
    def __init__(self, capacity=5000):
        self.capacity = capacity
        self.buffer = []
        self.priorities = []

    def push(self, state, action, reward, next_state):
        priority = abs(reward) + 0.1

        if len(self.buffer) < self.capacity:
            self.buffer.append((state, action, reward, next_state))
            self.priorities.append(priority)
        else:
            idx = random.randint(0, self.capacity - 1)
            self.buffer[idx] = (state, action, reward, next_state)
            self.priorities[idx] = priority

    def sample(self, batch_size):
        probs = np.array(self.priorities)
        probs = probs / probs.sum()

        indices = np.random.choice(len(self.buffer), batch_size, p=probs)

        return [self.buffer[i] for i in indices]

    def __len__(self):
        return len(self.buffer)
