from backend.core.actions.action_executor import ACTIONS, AUTONOMOUS_ALLOWED_ACTIONS
from backend.decision_engine_v2 import DecisionEngineV2


def test_unallowlisted_executable_action_cannot_auto_execute():
    engine = DecisionEngineV2.__new__(DecisionEngineV2)

    action = next(iter(ACTIONS.keys()))

    decision = engine._build_decision(
        "test decision",
        action,
        risk="HIGH",
        confidence=0.9,
        auto_execute=True,
    )

    assert action not in AUTONOMOUS_ALLOWED_ACTIONS
    assert decision["executable"] is True
    assert decision["auto_execute"] is False
    assert decision["requires_confirmation"] is True


def test_non_executable_action_requires_confirmation():
    engine = DecisionEngineV2.__new__(DecisionEngineV2)

    decision = engine._build_decision(
        "advisory decision",
        "observe",
        risk="MEDIUM",
        confidence=0.8,
        auto_execute=True,
    )

    assert decision["executable"] is False
    assert decision["auto_execute"] is False
    assert decision["requires_confirmation"] is True


def test_auto_execute_false_remains_false_for_allowed_action():
    engine = DecisionEngineV2.__new__(DecisionEngineV2)

    if not AUTONOMOUS_ALLOWED_ACTIONS:
        return

    action = next(iter(AUTONOMOUS_ALLOWED_ACTIONS))

    decision = engine._build_decision(
        "manual decision",
        action,
        risk="LOW",
        confidence=0.7,
        auto_execute=False,
    )

    assert decision["auto_execute"] is False
    assert decision["requires_confirmation"] is True


def test_process_kill_is_never_auto_executable():
    engine = DecisionEngineV2.__new__(DecisionEngineV2)

    for action in ("kill_process", "kill_high_cpu_process"):
        decision = engine._build_decision(
            "dangerous decision",
            action,
            risk="HIGH",
            confidence=1.0,
            auto_execute=True,
        )

        assert decision["auto_execute"] is False
        assert decision["requires_confirmation"] is True
