import pytest
from judgment.models import Judgment, Evidence


def test_confidence_bounds():
    j = Judgment(
        state="stable",
        confidence=0.5,
        impact_scope="none",
        urgency="ignore",
        recommended_posture="continue",
        evidence=[]
    )
    assert 0.0 <= j.confidence <= 1.0


def test_no_judgment_without_evidence():
    # Non-stable judgments MUST fail without evidence
    with pytest.raises(ValueError):
        Judgment(
            state="degraded",
            confidence=0.8,
            impact_scope="local",
            urgency="observe",
            recommended_posture="continue",
            evidence=[]
        )


def test_non_stable_judgment_with_evidence_is_allowed():
    j = Judgment(
        state="degraded",
        confidence=0.8,
        impact_scope="local",
        urgency="observe",
        recommended_posture="continue",
        evidence=[
            Evidence(
                source="cpu",
                observation="CPU usage elevated",
                baseline="30%",
                deviation="+25%"
            )
        ]
    )
    assert j.state == "degraded"
    assert len(j.evidence) == 1
