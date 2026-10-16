from datetime import datetime, timedelta, timezone

from judgment.engine import evaluate
from judgment.posture import resolve_posture


def _event(minutes_ago, severity, subsystem, event_type):
    timestamp = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {
        "timestamp": timestamp.isoformat(),
        "source": "test",
        "event_id": 18 if severity == "critical" else 1000,
        "event_type": event_type,
        "severity": severity,
        "subsystem": subsystem,
    }


def _event_judgments(facts):
    return [
        judgment for judgment in evaluate(facts, {})
        if any(
            getattr(evidence, "source", None) == "windows.event_log"
            for evidence in judgment.evidence
        )
    ]


def test_engine_uses_recent_events_and_current_resource_facts():
    facts = {
        "cpu": {"usage_percent": 30, "cores": 12},
        "memory": {"used_mb": 70, "total_mb": 100},
        "disk": {"used_percent": 50},
    }

    recent_hardware = _event_judgments(
        {
            **facts,
            "events": [
                _event(5, "critical", "hardware", "whea_hardware_error")
            ],
        }
    )
    assert recent_hardware
    assert recent_hardware[0].state == "risky"

    old_hardware = _event_judgments(
        {
            **facts,
            "events": [
                _event(120, "critical", "hardware", "whea_hardware_error")
            ],
        }
    )
    assert not old_hardware

    recent_crash = _event_judgments(
        {
            **facts,
            "events": [
                _event(5, "error", "application", "application_crash")
            ],
        }
    )
    assert recent_crash
    assert recent_crash[0].state == "degraded"

    old_crash = _event_judgments(
        {
            **facts,
            "events": [
                _event(120, "error", "application", "application_crash")
            ],
        }
    )
    assert not old_crash

    high_memory = evaluate(
        {
            **facts,
            "memory_used_mb": 97,
            "memory_total_mb": 100,
            "events": [],
        },
        {},
    )
    assert any(judgment.state == "risky" for judgment in high_memory)

    high_disk = evaluate(
        {**facts, "disk_used_percent": 93.5, "events": []},
        {},
    )
    constrained = [
        judgment for judgment in high_disk
        if judgment.state == "constrained"
    ]
    assert constrained
    assert resolve_posture(constrained).posture == "capacity-constrained"
