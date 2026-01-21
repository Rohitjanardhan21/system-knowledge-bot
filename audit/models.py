from dataclasses import dataclass
from typing import Literal

Outcome = Literal["spoken", "suppressed"]

@dataclass
class AuditEvent:
    timestamp: str
    source: str          # daemon | cli | can-run | chat | etc
    outcome: Outcome
    posture: str
    confidence: float
    reason: str
