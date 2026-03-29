CRITICAL_PROCESSES = ["postgres", "nginx", "docker"]

def is_critical(processes):
    for p in processes:
        if p["name"].lower() in CRITICAL_PROCESSES:
            return True
    return False
