# backend/feedback_engine.py

def evaluate_outcome(before: dict, after: dict) -> float:
    reward = 0.0

    before_cpu = before.get("cpu", 0)
    after_cpu = after.get("cpu", 0)

    before_mem = before.get("memory", 0)
    after_mem = after.get("memory", 0)

    # CPU improvement
    cpu_delta = before_cpu - after_cpu
    reward += max(min(cpu_delta / 50.0, 1.0), -1.0)

    # Memory improvement
    mem_delta = before_mem - after_mem
    reward += max(min(mem_delta / 50.0, 1.0), -1.0) * 0.7

    # Stability bonus
    if after_cpu < 60 and after_mem < 60:
        reward += 0.3

    return round(max(min(reward, 2.0), -2.0), 3)
ACTION_COST = {
    "kill_high_cpu_process": 0.5,
    "throttle_background_processes": 0.2,
    "maintain_state": 0.0
}


def evaluate_outcome(before, after, action):
    cpu_gain = before["cpu"] - after["cpu"]
    mem_gain = before["memory"] - after["memory"]

    reward = (cpu_gain * 0.5 + mem_gain * 0.3) / 50

    if after["cpu"] < 60:
        reward += 0.3

    reward -= ACTION_COST.get(action, 0)

    return round(max(min(reward, 2), -2), 3)
