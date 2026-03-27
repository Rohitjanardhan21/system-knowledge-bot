def system_chat(query: str, state: dict):
    cpu = state.get("cpu", 0)
    memory = state.get("memory", 0)

    if "cpu" in query.lower():
        return f"CPU is at {cpu}%. This indicates {'high load' if cpu > 80 else 'normal usage'}."

    if "memory" in query.lower():
        return f"Memory is at {memory}%. {'Pressure detected' if memory > 80 else 'Stable'}."

    return "System is operating within expected parameters."
