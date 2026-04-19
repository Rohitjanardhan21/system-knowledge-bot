# backend/vehicle_system/context_memory.py

class ContextMemory:

    def __init__(self):
        self.last_events = []

    def update(self, issues):
        self.last_events.extend(issues)
        self.last_events = self.last_events[-10:]

    def get_recent(self):
        return self.last_events


context_memory = ContextMemory()
