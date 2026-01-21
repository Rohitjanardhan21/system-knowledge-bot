from enum import Enum
from dataclasses import dataclass
from typing import Optional

from agent.intent import Intent
from agent.evidence import EvidenceStatus


# --------------------------------------------------
# Response modes
# --------------------------------------------------

class ResponseMode(Enum):
    ANSWER = "answer"
    EXPLAIN = "explain"
    VISUAL = "visual"
    REFUSE = "refuse"


# --------------------------------------------------
# Response object
# --------------------------------------------------

@dataclass
class AgentResponse:
    mode: ResponseMode
    text: str
    visual: Optional[dict] = None


# --------------------------------------------------
# Response mode selection
# --------------------------------------------------

def select_response_mode(intent: Intent, evidence: EvidenceStatus) -> ResponseMode:
    if evidence != EvidenceStatus.SUFFICIENT:
        return ResponseMode.REFUSE

    if intent == Intent.EXPLAIN:
        return ResponseMode.EXPLAIN

    if intent in (Intent.VISUALIZE, Intent.HISTORY):
        return ResponseMode.VISUAL

    if intent == Intent.STATUS:
        return ResponseMode.ANSWER

    return ResponseMode.REFUSE


# --------------------------------------------------
# Concrete response helpers
# --------------------------------------------------

def refuse_response(reason: Optional[str] = None) -> AgentResponse:
    """
    Conservative refusal. Reason is intentionally not exposed to user.
    """
    return AgentResponse(
        mode=ResponseMode.REFUSE,
        text=(
            "I understand what you're asking. "
            "I don’t have enough verified system evidence to answer that reliably."
        )
    )


def answer_response(text: str) -> AgentResponse:
    return AgentResponse(
        mode=ResponseMode.ANSWER,
        text=text
    )


def explain_response(text: str) -> AgentResponse:
    return AgentResponse(
        mode=ResponseMode.EXPLAIN,
        text=text
    )


def visual_response(summary: str, visual_data: dict) -> AgentResponse:
    return AgentResponse(
        mode=ResponseMode.VISUAL,
        text=summary,
        visual=visual_data
    )
