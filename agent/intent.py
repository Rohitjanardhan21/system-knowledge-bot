from enum import Enum
from dataclasses import dataclass
from typing import List


# ==================================================
# Intent definitions
# ==================================================

class Intent(Enum):
    STATUS = "status"         # current state / health
    EXPLAIN = "explain"       # why / how something works
    HISTORY = "history"       # over time / today / timeline
    VISUALIZE = "visualize"   # show / graph / chart
    CAPABILITY = "capability" # can-run / feasibility
    UNKNOWN = "unknown"


# ==================================================
# Intent resolution result
# ==================================================

@dataclass
class IntentResult:
    intent: Intent


# ==================================================
# Intent resolution logic
# ==================================================

def resolve_intent(tokens: List[str]) -> IntentResult:
    """
    Resolve user intent from normalized tokens.

    Rules:
    - HISTORY must be detected before VISUALIZE
    - STATUS is the default for health/state questions
    - UNKNOWN is explicit and safe
    """

    t = set(tokens)

    # --------------------------------------------------
    # HISTORY / TEMPORAL (highest priority)
    # --------------------------------------------------
    if any(word in t for word in (
        "today",
        "timeline",
        "history",
        "earlier",
        "previous",
        "before",
        "over",
        "trend",
        "trends",
    )):
        return IntentResult(Intent.HISTORY)

    # --------------------------------------------------
    # VISUALIZATION
    # --------------------------------------------------
    if any(word in t for word in (
        "show",
        "visual",
        "visualize",
        "graph",
        "chart",
        "plot",
    )):
        return IntentResult(Intent.VISUALIZE)

    # --------------------------------------------------
    # EXPLANATION
    # --------------------------------------------------
    if any(word in t for word in (
        "why",
        "explain",
        "reason",
        "how",
    )):
        return IntentResult(Intent.EXPLAIN)

    # --------------------------------------------------
    # CAPABILITY / FEASIBILITY
    # --------------------------------------------------
    if any(word in t for word in (
        "can",
        "handle",
        "run",
        "support",
        "capable",
    )):
        return IntentResult(Intent.CAPABILITY)

    # --------------------------------------------------
    # STATUS / HEALTH
    # --------------------------------------------------
    if any(word in t for word in (
        "status",
        "health",
        "healthy",
        "state",
        "ok",
    )):
        return IntentResult(Intent.STATUS)

    # --------------------------------------------------
    # Fallback (explicit)
    # --------------------------------------------------
    return IntentResult(Intent.UNKNOWN)
