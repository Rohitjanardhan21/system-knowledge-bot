from enum import Enum
from dataclasses import dataclass
from typing import List


class Intent(str, Enum):
    STATUS = "status"
    EXPLAIN = "explain"
    VISUAL = "visual"
    CAPABILITY = "capability"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    intent: Intent
    confidence: float


STATUS_WORDS = {
    "status", "health", "state", "posture", "condition", "ok", "okay",
    "running", "idle", "busy", "normal"
}

EXPLAIN_WORDS = {
    "why", "explain", "reason", "cause", "because", "meaning"
}

VISUAL_WORDS = {
    "show", "graph", "timeline", "visualize", "chart", "plot", "today",
    "history"
}

CAPABILITY_WORDS = {
    "can", "handle", "run", "support", "capable", "preflight"
}


def resolve_intent(tokens: List[str]) -> IntentResult:

    token_set = set(tokens)

    if token_set & VISUAL_WORDS:
        return IntentResult(Intent.VISUAL, 0.9)

    if token_set & EXPLAIN_WORDS:
        return IntentResult(Intent.EXPLAIN, 0.8)

    if token_set & CAPABILITY_WORDS:
        return IntentResult(Intent.CAPABILITY, 0.8)

    if token_set & STATUS_WORDS:
        return IntentResult(Intent.STATUS, 0.7)

    return IntentResult(Intent.UNKNOWN, 0.0)
