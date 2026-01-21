import json
from pathlib import Path
from datetime import datetime

from preflight.evaluator import evaluate_preflight
from audit.logger import log_event
from audit.models import AuditEvent

STATE_FILE = Path("system_state/latest.json")

def can_run(job_name: str):
    if not STATE_FILE.exists():
        print("System state unavailable. Cannot evaluate readiness.")
        return

    with open(STATE_FILE) as f:
        state = json.load(f)

    posture = state["posture"]["posture"]
    judgments = state["judgments"]

    result = evaluate_preflight(posture, judgments)

    print(f"Preflight check for: {job_name}\n")
    print(f"System posture: {result.posture}")
    print(f"Decision: {result.decision.upper()} (confidence {result.confidence:.2f})\n")
    print(result.reasoning)

    # 🔒 AUDIT — explicit command = explicit log
    log_event(AuditEvent(
        timestamp=datetime.utcnow().isoformat(),
        source="can-run",
        outcome="spoken",
        posture=result.posture,
        confidence=result.confidence,
        reason="User explicitly requested preflight evaluation"
    ))
