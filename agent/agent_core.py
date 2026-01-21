from datetime import date

from agent.normalize import normalize_question
from agent.domain import resolve_domains
from agent.intent import resolve_intent, Intent
from agent.evidence import check_evidence, EvidenceStatus
from agent.respond import (
    select_response_mode,
    ResponseMode,
    refuse_response,
    answer_response,
    visual_response,
)

from timeline.durations import compute_posture_durations


# --------------------------------------------------
# Agent entry point
# --------------------------------------------------

def handle_question(user_input: str, facts: dict):
    """
    Main agent entry point.
    Accepts raw user input and current system facts.
    Returns an AgentResponse.
    """

    # --------------------------------------------------
    # 1. Normalize question
    # --------------------------------------------------
    nq = normalize_question(user_input)

    # --------------------------------------------------
    # 2. Domain validation (authority check)
    # --------------------------------------------------
    domain_result = resolve_domains(nq.tokens)
    if not domain_result.allowed:
        return refuse_response("domain")

    # --------------------------------------------------
    # 3. Intent resolution
    # --------------------------------------------------
    intent_result = resolve_intent(nq.tokens)

    if intent_result.intent == Intent.UNKNOWN:
        return refuse_response("intent")

    # --------------------------------------------------
    # 4. Evidence gating
    # --------------------------------------------------
    evidence_result = check_evidence(
        domain_result.domains,
        intent_result.intent,
        facts
    )

    # --------------------------------------------------
    # 5. Response mode selection
    # --------------------------------------------------
    mode = select_response_mode(
        intent_result.intent,
        evidence_result.status
    )

    if mode == ResponseMode.REFUSE:
        return refuse_response("evidence")

    # --------------------------------------------------
    # 6. Response execution (minimal, factual, calm)
    # --------------------------------------------------

    # -------- STATUS --------
    if mode == ResponseMode.ANSWER:
        return answer_response(
            "Based on current system state, no abnormal behavior is observed."
        )

    # -------- EXPLANATION --------
    if mode == ResponseMode.EXPLAIN:
        return answer_response(
            "This behavior is consistent with observed resource usage patterns "
            "on this system and does not indicate an error."
        )

    # -------- VISUALIZATION --------
    if mode == ResponseMode.VISUAL:
        today = date.today().isoformat()
        timeline = compute_posture_durations(today)

        return visual_response(
            "This view summarizes system posture over the course of today. "
            "Colors indicate operating posture, not errors.",
            visual_data={
                "type": "posture_timeline",
                "title": "System posture today",
                "data": timeline
            }
        )

    # --------------------------------------------------
    # 7. Safety fallback (should never be reached)
    # --------------------------------------------------
    return refuse_response("unknown")
