def can_answer(intent, available_facts: dict) -> bool:
    if intent == "gpu_status":
        return "gpu" in available_facts

    if intent == "thermal_status":
        return "temperature" in available_facts

    return True
