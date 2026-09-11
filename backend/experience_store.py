# backend/experience_store.py

import json
from datetime import datetime, timezone

PATH = "system_facts/experiences.json"

def store_experience(state, action, reward, before, after, verification=None):
    exp = {
        "state": state,
        "action": action,
        "reward": reward,
        "before": before,
        "after": after,
        "verification": verification,
        "time": datetime.now(timezone.utc).isoformat()
    }

    try:
        data = json.load(open(PATH))
    except:
        data = []

    data.append(exp)

    json.dump(data[-500:], open(PATH, "w"), indent=2)
