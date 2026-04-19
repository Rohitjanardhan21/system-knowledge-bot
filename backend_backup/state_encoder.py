# backend/state_encoder.py

def encode_state(metrics: dict) -> str:
    cpu = metrics.get("cpu", 0)
    mem = metrics.get("memory", 0)

    # CPU
    if cpu >= 85:
        cpu_state = "cpu_high"
    elif cpu >= 60:
        cpu_state = "cpu_moderate"
    else:
        cpu_state = "cpu_normal"

    # Memory
    if mem >= 85:
        mem_state = "mem_high"
    elif mem >= 60:
        mem_state = "mem_moderate"
    else:
        mem_state = "mem_normal"

    return f"{cpu_state}|{mem_state}"
