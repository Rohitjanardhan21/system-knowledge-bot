from intent.intents import Intent

INTENT_KEYWORDS = {
    Intent.SYSTEM_HEALTH: [
        "healthy", "health", "status", "overall", "ok"
    ],
    Intent.CPU_STATUS: [
        "cpu", "processor", "cores", "load"
    ],
    Intent.MEMORY_STATUS: [
        "ram", "memory", "swap"
    ],
    Intent.GPU_STATUS: [
        "gpu", "graphics", "vram"
    ],
    Intent.THERMAL_STATUS: [
        "temperature", "temp", "heat", "thermal"
    ],
    Intent.BOTTLENECK: [
        "slow", "lag", "bottleneck", "performance"
    ],
    Intent.CAPABILITY: [
        "can i", "handle", "run", "support"
    ],
    Intent.SUGGESTIONS: [
        "what should", "suggest", "improve", "optimize"
    ],
    Intent.EXPLAIN_SILENCE: [
        "why didn't", "why no", "silent", "didn't alert"
    ],
    Intent.EXPLAIN_SYSTEM: [
        "how does", "how does this", "how cpu", "how memory"
    ],
}

def parse_intent(question: str) -> Intent:
    q = question.lower()

    scores = {}

    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in q)
        if score > 0:
            scores[intent] = score

    if not scores:
        return Intent.UNKNOWN

    return max(scores, key=scores.get)
