from datetime import date

from agent.normalize import normalize_question
from agent.domain import resolve_domains
from agent.intent import resolve_intent, Intent
from agent.evidence import check_evidence
from agent.respond import (
    select_response_mode,
    refuse_response,
    answer_response,
    visual_response,
)
from agent.types import ResponseMode

from timeline.visualize import posture_timeline_visual


def handle_question(user_input: str, facts: dict):

    nq = normalize_question(user_input)

    domain_result = resolve_domains(nq.tokens)
    print("DOMAIN RESULT:", domain_result)
    if not domain_result.allowed:
        return refuse_response("domain")

    intent_result = resolve_intent(nq.tokens)
    if intent_result.intent == Intent.UNKNOWN:
        return refuse_response("intent")

    evidence_status = check_evidence(
        domain_result.domains,
        intent_result.intent,
        facts
    )

    mode = select_response_mode(
        intent_result.intent,
        evidence_status
    )

    if mode == ResponseMode.REFUSE:
        return refuse_response("evidence")

    if mode == ResponseMode.ANSWER:
        return answer_response(
            "Based on current system state, no abnormal behavior is observed."
        )

    if mode == ResponseMode.EXPLAIN:
        return answer_response(
            "This behavior is consistent with observed resource usage patterns "
            "and does not indicate an error."
        )

    if mode == ResponseMode.VISUAL:

        timeline = posture_timeline_visual()

        return visual_response(
            "This view summarizes system posture over the course of today.",
            visual_data={
                "type": "posture_timeline",
                "title": "System posture today",
                "data": timeline
            }
        )

    return refuse_response("unknown")
