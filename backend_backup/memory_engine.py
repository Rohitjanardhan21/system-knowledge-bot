import json
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path("system_facts/memory.json")


# -------------------------------------------------
# 🧠 MEMORY ENGINE
# -------------------------------------------------
class MemoryEngine:

    def __init__(self):
        if not MEMORY_FILE.exists():
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
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


# -------------------------------------------------
# 🔥 GLOBAL SYSTEM PROFILE
# -------------------------------------------------
system_profile = None


# -------------------------------------------------
# 🚀 INITIALIZE PROFILE (SAFE)
# -------------------------------------------------
def init_system_profile():
    global system_profile

    try:
        from backend.system_profiler import profile_system
        system_profile = profile_system()

        # Safety check
        if not isinstance(system_profile, dict):
            raise ValueError("Invalid profile format")

    except Exception as e:
        print("⚠️ Profile init failed:", e)

        # Fallback profile
        system_profile = {
            "memory": {
                "total_gb": 8
            },
            "cpu": {
                "cores": 4
            }
        }


# -------------------------------------------------
# 🔍 GET PROFILE (SELF-HEALING)
# -------------------------------------------------
def get_system_profile():
    global system_profile

    if system_profile is None:
        try:
            from backend.system_profiler import profile_system
            system_profile = profile_system()

            if not isinstance(system_profile, dict):
                raise ValueError("Invalid profile format")

        except Exception as e:
            print("⚠️ Failed to load system profile:", e)

            # Fallback profile
            system_profile = {
                "memory": {
                    "total_gb": 8
                },
                "cpu": {
                    "cores": 4
                }
            }

    return system_profile
