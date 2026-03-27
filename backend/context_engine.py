def detect_context(processes):

    if not processes:
        return "idle"

    top = max(processes, key=lambda p: p.get("cpu", 0))
    name = (top.get("name") or "").lower()

    if "chrome" in name:
        return "browsing"

    if "code" in name or "pycharm" in name:
        return "development"

    if "game" in name or "steam" in name:
        return "gaming"

    return "general"
