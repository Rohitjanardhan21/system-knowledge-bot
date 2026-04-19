from collections import deque
from datetime import datetime


class AgentMemory:

    def __init__(self, max_history=20):
        self.history = deque(maxlen=max_history)
        self.last_state = None

    # -------------------------------------------------
    # STORE INTERACTION
    # -------------------------------------------------
    def add(self, query, response, state):
        self.history.append({
            "time": datetime.now().isoformat(),
            "query": query,
            "response": response,
            "state": state
        })
        self.last_state = state

    # -------------------------------------------------
    # GET HISTORY
    # -------------------------------------------------
    def get_recent(self):
        return list(self.history)

    # -------------------------------------------------
    # DETECT CHANGE
    # -------------------------------------------------
    def detect_change(self, new_state):
        if not self.last_state:
            return "No previous data to compare."

        prev_cpu = self.last_state.get("cpu", 0)
        curr_cpu = new_state.get("cpu", 0)

        diff = curr_cpu - prev_cpu

        if abs(diff) < 5:
            return "System is relatively stable."

        if diff > 0:
            return f"CPU increased by {round(diff,1)}% recently."
        else:
            return f"CPU decreased by {round(abs(diff),1)}% recently."
