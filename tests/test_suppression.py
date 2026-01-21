from judgment.suppression import should_speak
from judgment.models import Judgment, Evidence


def make_judgment(confidence, urgency):
    return Judgment(
        state="degraded",
        confidence=confidence,
        impact_scope="local",
        urgency=urgency,
        recommended_posture="continue",
        evidence=[
            Evidence(
                source="cpu",
                observation="CPU elevated",
                baseline="30%",
                deviation="+20%"
            )
        ]
    )


def test_does_not_speak_when_not_asked_and_low_confidence():
    j = make_judgment(confidence=0.4, urgency="observe")
    assert should_speak(j, user_asked=False) is False


def test_speaks_when_user_asked():
    j = make_judgment(confidence=0.2, urgency="ignore")
    assert should_speak(j, user_asked=True) is True


def test_speaks_on_urgent_condition():
    j = make_judgment(confidence=0.9, urgency="act-now")
    assert should_speak(j, user_asked=False) is True
