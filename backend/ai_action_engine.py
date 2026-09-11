"""
AI Action Engine
----------------
Transforms AI/system insights into safe, structured, human-reviewable actions.
"""

import re
import uuid
from typing import Dict, Any, Optional


def build_action(
    action_type: str,
    target: str,
    reason: str,
    confidence: float,
    risk: str = "medium",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": action_type,
        "target": target,
        "reason": reason,
        "confidence": round(confidence, 2),
        "risk": risk,
        "status": "proposed",
        "requires_approval": True,
        "metadata": metadata or {},
    }


def extract_from_metrics(
    system_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Extract actions from structured system data without AI hallucination."""

    root = system_data.get("root_cause", {})
    cpu = system_data.get("cpu", 0)
    memory = system_data.get("memory", 0)
    anomalies = system_data.get("anomalies", [])

    if not root:
        return None

    process = root.get("process", "unknown")
    process_cpu = root.get("cpu", 0)

    if process_cpu > 70:
        return build_action(
            action_type="terminate_process",
            target=process,
            reason=f"{process} consuming {process_cpu}% CPU",
            confidence=0.85,
            risk="high",
        )

    if memory > 85:
        return build_action(
            action_type="free_memory",
            target="system",
            reason=f"Memory usage at {memory}%",
            confidence=0.75,
            risk="medium",
        )

    if anomalies:
        return build_action(
            action_type="investigate_anomaly",
            target=anomalies[0]["metric"],
            reason="Statistical anomaly detected",
            confidence=0.8,
            risk="medium",
        )

    return None


def extract_from_llm(ai_text: str) -> Optional[Dict[str, Any]]:
    """Parse only clear action intent from LLM output."""

    if not ai_text:
        return None

    text = ai_text.lower()

    match = re.search(r"(kill|terminate|stop)\s+(\w+)", text)
    if match:
        process = match.group(2)
        return build_action(
            action_type="terminate_process",
            target=process,
            reason="Suggested by AI analysis",
            confidence=0.7,
            risk="high",
        )

    match = re.search(r"restart\s+(\w+)", text)
    if match:
        service = match.group(1)
        return build_action(
            action_type="restart_service",
            target=service,
            reason="AI suggested restart",
            confidence=0.65,
            risk="medium",
        )

    if "scale" in text or "increase resources" in text:
        return build_action(
            action_type="scale_resources",
            target="system",
            reason="AI suggested scaling resources",
            confidence=0.6,
            risk="medium",
        )

    return None


def generate_action(
    system_data: Dict[str, Any],
    ai_response: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Priority:
    1. Deterministic system signals
    2. Validated AI suggestions
    """

    action = extract_from_metrics(system_data)
    if action:
        return action

    if ai_response:
        action = extract_from_llm(ai_response)
        if action:
            return action

    return None


def validate_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """Enforce safety constraints."""

    if not action:
        return {}

    dangerous = ["shutdown_system", "format_disk"]

    if action["type"] in dangerous:
        action["blocked"] = True
        action["reason_blocked"] = "Dangerous action not allowed"
        return action

    action["requires_approval"] = True

    return action


def propose_action(
    system_data: Dict[str, Any],
    ai_response: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Public interface used by legacy action routes."""

    action = generate_action(system_data, ai_response)

    if not action:
        return None

    return validate_action(action)
