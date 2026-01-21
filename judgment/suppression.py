from datetime import datetime
from audit.logger import log_event
from audit.models import AuditEvent

CONFIDENCE_THRESHOLD = 0.65

def should_speak(judgment, user_asked: bool, source="unknown") -> bool:
    ts = datetime.utcnow().isoformat()

    if user_asked:
        log_event(AuditEvent(
            timestamp=ts,
            source=source,
            outcome="spoken",
            posture="n/a",
            confidence=judgment.confidence,
            reason="User explicitly requested output"
        ))
        return True

    if judgment.confidence < CONFIDENCE_THRESHOLD:
        log_event(AuditEvent(
            timestamp=ts,
            source=source,
            outcome="suppressed",
            posture="n/a",
            confidence=judgment.confidence,
            reason="Confidence below threshold"
        ))
        return False

    if judgment.urgency == "act-now":
        log_event(AuditEvent(
            timestamp=ts,
            source=source,
            outcome="spoken",
            posture="n/a",
            confidence=judgment.confidence,
            reason="Urgent condition requires visibility"
        ))
        return True

    log_event(AuditEvent(
        timestamp=ts,
        source=source,
        outcome="suppressed",
        posture="n/a",
        confidence=judgment.confidence,
        reason="No urgency and no user request"
    ))
    return False
