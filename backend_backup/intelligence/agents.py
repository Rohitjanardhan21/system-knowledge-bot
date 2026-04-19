class BaseAgent:
    def __init__(self, name):
        self.name = name

    def decide(self, state):
        return "maintain_state"


class CPUAgent(BaseAgent):
    def decide(self, state):
        if state["cpu"] > 75:
            return "throttle_background_processes"
        return "maintain_state"


class MemoryAgent(BaseAgent):
    def decide(self, state):
        if state["memory"] > 80:
            return "free_memory_cache"
        return "maintain_state"


class DiskAgent(BaseAgent):
    def decide(self, state):
        if state["disk"] > 85:
            return "reduce_disk_io"
        return "maintain_state"


class AgentCoordinator:
    def __init__(self):
        self.agents = [
            CPUAgent("cpu"),
            MemoryAgent("memory"),
            DiskAgent("disk"),
        ]

    def decide(self, state):
        votes = {}

        for agent in self.agents:
            action = agent.decide(state)
            votes[action] = votes.get(action, 0) + 1

        return max(votes, key=votes.get)
