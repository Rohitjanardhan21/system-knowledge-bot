# backend/experience_store.py

import json
from datetime import datetime

PATH = "system_facts/experiences.json"

def store_experience(state, action, reward, before, after):
    exp = {
        "state": state,
        "action": action,
        "reward": reward,
        "before": before,
        "after": after,
        "time": datetime.utcnow().isoformat()
    }

    try:
        data = json.load(open(PATH))
    except:
        data = []

    data.append(exp)

    json.dump(data[-500:], open(PATH, "w"), indent=2)
