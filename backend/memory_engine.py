import json
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path("system_facts/memory.json")

class MemoryEngine:

    def __init__(self):
        if not MEMORY_FILE.exists():
            MEMORY_FILE.write_text(json.dumps([]))

    def store(self, entry):
        data = json.loads(MEMORY_FILE.read_text())
        data.append({
            "time": datetime.utcnow().isoformat(),
            **entry
        })
        MEMORY_FILE.write_text(json.dumps(data, indent=2))

    def get_recent(self, limit=20):
        data = json.loads(MEMORY_FILE.read_text())
        return data[-limit:]
system_profile = None

def init_system_profile():
    global system_profile
    from backend.system_profiler import profile_system
    system_profile = profile_system()

def get_system_profile():
    return system_profile
