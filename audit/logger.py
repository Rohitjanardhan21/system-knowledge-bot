from pathlib import Path
from audit.models import AuditEvent

AUDIT_DIR = Path("bot_audit")
AUDIT_DIR.mkdir(exist_ok=True)

DECISION_LOG = AUDIT_DIR / "decisions.log"
SHADOW_LOG = AUDIT_DIR / "shadow.log"

def log_event(event: AuditEvent):
    line = (
        f"{event.timestamp} | "
        f"{event.source} | "
        f"{event.outcome} | "
        f"{event.posture} | "
        f"{event.confidence:.2f} | "
        f"{event.reason}\n"
    )

    target = DECISION_LOG if event.outcome == "spoken" else SHADOW_LOG

    try:
        with open(target, "a") as f:
            f.write(line)
    except Exception:
        # Audit must NEVER affect system behavior
        pass
