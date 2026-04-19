# backend/safety_guard.py

BLOCKED_ACTIONS = ["shutdown", "kill_system"]

CRITICAL_PROCESSES = ["systemd", "init", "kernel"]


def is_safe(action, process_name=None):
    if action in BLOCKED_ACTIONS:
        return False

    if process_name and process_name.lower() in CRITICAL_PROCESSES:
        return False

    return True
