import json
from pathlib import Path

OPT_FILE = Path("system_facts/self_opt.json")
OPT_FILE.parent.mkdir(exist_ok=True)

DEFAULT = {
    "epsilon": 1.0,
    "reward_scale": 1.0,
    "mode_scores": {
        "high_performance": 0,
        "balanced": 0,
        "lightweight": 0
    }
}


def load_opt():
    if OPT_FILE.exists():
        return json.loads(OPT_FILE.read_text())
    return DEFAULT.copy()


def save_opt(data):
    OPT_FILE.write_text(json.dumps(data, indent=2))


# -----------------------------------------
# 🔥 UPDATE BASED ON EXPERIENCE
# -----------------------------------------
def update_optimizer(mode, reward):

    data = load_opt()

    # update mode performance
    data["mode_scores"][mode] += reward

    # 🔥 adaptive epsilon
    if reward > 0:
        data["epsilon"] *= 0.98
    else:
        data["epsilon"] = min(1.0, data["epsilon"] + 0.05)

    # 🔥 reward scaling
    if reward < 0:
        data["reward_scale"] *= 1.05
    else:
        data["reward_scale"] *= 0.99

    save_opt(data)


def get_optimizer():
    return load_opt()
