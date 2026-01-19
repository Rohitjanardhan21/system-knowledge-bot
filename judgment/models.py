# ==========================================================
# REASONING CONTRACT — DO NOT MODIFY LIGHTLY
#
# This file defines the stable reasoning data contracts for
# System Knowledge Bot.
#
# Any change to this file REQUIRES:
# - Updated tests
# - Explicit review
# - Version bump
#
# Breaking this contract breaks trust.
# ==========================================================

from dataclasses import dataclass
from typing import List, Literal, Optional


# -------------------------
# Enumerated domain values
# -------------------------

State = Literal[
    "stable",
    "degraded",
    "constrained",
    "risky"
]

Urgency = Literal[
    "ignore",
    "observe",
    "act-soon",
    "act-now"
]

ImpactScope = Literal[
    "none",
    "local",
    "system-wide"
]

RecommendedPosture = Literal[
    "continue",
    "delay",
    "stop",
    "investigate"
]

SystemPosture = Literal[
    "idle-capable",
    "work-stable",
    "performance-sensitive",
    "capacity-constrained",
    "recovery-required"
]


# -------------------------
# Evidence model
# -------------------------

@dataclass(frozen=True)
class Evidence:
    """
    A single factual observation that supports a judgment.
    Evidence must be observable and non-speculative.
    """
    source: str
    observation: str
    baseline: Optional[str]
    deviation: Optional[str]


# -------------------------
# Judgment model
# -------------------------

@dataclass(frozen=True)
class Judgment:
    """
    A structured operational judgment derived from system facts.

    Judgments enforce internal invariants:
    - Confidence must be between 0.0 and 1.0
    - Non-stable judgments MUST have evidence
    """

    state: State
    confidence: float
    evidence: List[Evidence]

    impact_scope: ImpactScope
    urgency: Urgency
    recommended_posture: RecommendedPosture

    def __post_init__(self):
        # Confidence bounds
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"Judgment confidence out of bounds: {self.confidence}"
            )

        # Evidence requirement
        if self.state != "stable" and not self.evidence:
            raise ValueError(
                "Non-stable judgments must include supporting evidence"
            )


# -------------------------
# System posture resolution
# -------------------------

@dataclass(frozen=True)
class SystemPostureResult:
    """
    Human-facing interpretation of overall system condition.
    """
    posture: SystemPosture
    reasoning: str
