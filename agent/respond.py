from typing import Optional, Dict, Any

from agent.types import EvidenceStatus, ResponseMode


# --------------------------------------------------
# Response container
# --------------------------------------------------

class AgentResponse(dict):
    """
    Thin dict wrapper for agent output payloads.
    """
    pass


# --------------------------------------------------
# Refusal Response
# --------------------------------------------------

def refuse_response(
    reason: Optional[str] = None,
    confidence: float = 0.0,
    evidence: str = "insufficient telemetry",
) -> AgentResponse:

    return {
        "mode": ResponseMode.REFUSE.value,
        "text": (
            "I understand what you're asking. "
            "I don’t have enough verified system evidence to answer that reliably."
        ),
        "visual": None,
        "confidence": confidence,
        "evidence": evidence,
        "reason": reason,
    }


# --------------------------------------------------
# Answer Response
# --------------------------------------------------

def answer_response(
    text: str,
    confidence: float = 1.0,
    evidence: str = "strong",
) -> AgentResponse:

    return {
        "mode": ResponseMode.ANSWER.value,
        "text": text,
        "visual": None,
        "confidence": confidence,
        "evidence": evidence,
        "reason": None,
    }


# --------------------------------------------------
# Visual Response
# --------------------------------------------------

def visual_response(
    text: str,
    visual_data: Dict[str, Any],
    confidence: float = 1.0,
    evidence: str = "strong",
) -> AgentResponse:

    return {
        "mode": ResponseMode.VISUAL.value,
        "text": text,
        "visual": visual_data,
        "confidence": confidence,
        "evidence": evidence,
        "reason": None,
    }


# --------------------------------------------------
# Mode Selector
# --------------------------------------------------

def select_response_mode(intent, evidence_status: EvidenceStatus) -> ResponseMode:
    """
    Determines the high-level response mode
    based on intent + evidence sufficiency.
    """

    if evidence_status == EvidenceStatus.INSUFFICIENT:
        return ResponseMode.REFUSE

    intent_name = intent.name.lower()

    if intent_name in ("visualize", "timeline", "show"):
        return ResponseMode.VISUAL

    if intent_name in ("explain",):
        return ResponseMode.EXPLAIN

    return ResponseMode.ANSWER
