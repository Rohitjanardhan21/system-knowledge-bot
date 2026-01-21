from dataclasses import dataclass
from typing import Literal

Decision = Literal["safe", "risky", "defer"]

@dataclass
class PreflightResult:
    decision: Decision
    confidence: float
    reasoning: str
    posture: str
