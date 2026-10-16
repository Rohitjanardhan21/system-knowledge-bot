from judgment.models import Judgment, Evidence
from judgment.trend import analyze_history
from datetime import datetime, timezone


def _trend_evidence(source, trend):
    return Evidence(
        source=source,
        observation=f"Historical trend: {trend}",
        baseline="Stable historical telemetry",
        deviation=f"Historical telemetry is classified as {trend}",
    )


def _adjust_confidence(confidence, trend):
    """
    Apply a conservative temporal adjustment.

    Worsening/persistent trends strengthen an existing condition.
    Recovering trends slightly reduce confidence.
    Volatile/insufficient trends do not change confidence.
    """
    if trend == "worsening":
        return min(1.0, confidence + 0.03)

    if trend == "persistent":
        return min(1.0, confidence + 0.01)

    if trend == "recovering":
        return max(0.0, confidence - 0.02)

    return confidence


def evaluate(facts: dict, baseline: dict) -> list[Judgment]:
    history = facts.get("history", [])

    trends = analyze_history(history) if history else {
        "cpu": {"trend": "insufficient-data"},
        "memory": {"trend": "insufficient-data"},
        "disk": {"trend": "insufficient-data"},
    }

    cpu_trend = trends["cpu"]["trend"]
    memory_trend = trends["memory"]["trend"]
    disk_trend = trends["disk"]["trend"]

    judgments = []

    # -------- CPU --------
    cpu_usage = facts.get("cpu_usage", 0.0)
    if not cpu_usage:
        cpu = facts.get("cpu", {})
        cpu_usage = cpu.get("usage_percent", 0.0) if isinstance(cpu, dict) else cpu

    # -------- MEMORY --------
    memory_used = facts.get("memory_used_mb", 0.0)
    if not memory_used:
        memory = facts.get("memory", {})
        memory_used = memory.get("used_mb", 0.0) if isinstance(memory, dict) else memory

    memory_total = facts.get("memory_total_mb", 0.0)
    if not memory_total:
        memory = facts.get("memory", {})
        memory_total = memory.get("total_mb", 0.0) if isinstance(memory, dict) else 0.0

    # -------- DISK --------
    disk_used = facts.get("disk_used_percent", 0.0)
    if not disk_used:
        disk = facts.get("disk", {})
        disk_used = disk.get("used_percent", 0.0) if isinstance(disk, dict) else disk

    # -------- CPU PRESSURE --------
    if cpu_usage > 85:
        state = "risky" if cpu_usage > 95 else "constrained"

        judgments.append(
            Judgment(
                state=state,
                confidence=_adjust_confidence(
                    min(1.0, cpu_usage / 100.0),
                    cpu_trend,
                ),
                evidence=[
                    Evidence(
                        source="system.cpu",
                        observation=f"CPU utilization is {cpu_usage:.1f}%",
                        baseline="CPU utilization below 85%",
                        deviation=f"CPU utilization exceeds 85% threshold"
                    ),
                    _trend_evidence("history.cpu", cpu_trend),
                ],
                impact_scope="local",
                urgency="act-now" if cpu_usage > 95 else "act-soon",
                recommended_posture="stop" if cpu_usage > 95 else "delay",
            )
        )

    # -------- MEMORY PRESSURE --------
    if memory_total > 0:
        mem_ratio = memory_used / memory_total

        if mem_ratio > 0.90:
            state = "risky" if mem_ratio > 0.95 else "constrained"

            judgments.append(
                Judgment(
                    state=state,
                    confidence=_adjust_confidence(
                        min(1.0, mem_ratio),
                        memory_trend,
                    ),
                    evidence=[
                        Evidence(
                            source="system.memory",
                            observation=(
                                f"Memory utilization is {mem_ratio * 100:.1f}% "
                                f"({memory_used:.1f}/{memory_total:.1f} MB)"
                            ),
                            baseline="Memory utilization below 90%",
                            deviation="Memory utilization exceeds 90% threshold",
                        ),
                        _trend_evidence("history.memory", memory_trend),
                    ],
                    impact_scope="system-wide",
                    urgency="act-now" if mem_ratio > 0.95 else "act-soon",
                    recommended_posture="stop" if mem_ratio > 0.95 else "delay",
                )
            )

    # -------- DISK PRESSURE --------
    if disk_used > 90:
        state = "risky" if disk_used > 95 else "constrained"

        judgments.append(
            Judgment(
                state=state,
                confidence=_adjust_confidence(
                    min(1.0, disk_used / 100.0),
                    disk_trend,
                ),
                evidence=[
                    Evidence(
                        source="system.storage",
                        observation=f"Disk utilization is {disk_used:.1f}%",
                        baseline="Disk utilization below 90%",
                        deviation="Disk utilization exceeds 90% threshold",
                    ),
                    _trend_evidence("history.disk", disk_trend),
                ],
                impact_scope="system-wide",
                urgency="act-now" if disk_used > 95 else "act-soon",
                recommended_posture="stop" if disk_used > 95 else "investigate",
            )
        )

    # -------- EVENT / FAILURE SIGNALS --------
    # Historical trend information is available to the
    # judgment layer without changing existing thresholds.
    events = facts.get("events", [])


    # -------- EVENT TEMPORAL FILTERING --------
    # Events remain preserved in facts, but only recent
    # events contribute to the current active posture.
    EVENT_ACTIVE_WINDOW_MINUTES = 30

    recent_events = []

    if events:
        now = datetime.now(timezone.utc)

        for event in events:
            timestamp = event.get("timestamp")

            if not timestamp:
                continue

            try:
                event_time = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                )

                if event_time.tzinfo is None:
                    event_time = event_time.replace(
                        tzinfo=timezone.utc
                    )

                age_minutes = (
                    now - event_time
                ).total_seconds() / 60.0

                if 0 <= age_minutes <= EVENT_ACTIVE_WINDOW_MINUTES:
                    recent_events.append(event)

            except (ValueError, TypeError):
                continue

    # Only recent events affect active judgments.
    if recent_events:
        critical_hardware = [
            e for e in recent_events
            if e.get("severity") == "critical"
            and e.get("subsystem") == "hardware"
        ]

        hardware_errors = [
            e for e in recent_events
            if e.get("severity") in ("error", "critical")
            and e.get("subsystem") == "hardware"
        ]

        application_crashes = [
            e for e in recent_events
            if e.get("event_type") == "application_crash"
            or e.get("event_id") == 1000
        ]

        if critical_hardware:
            confidence = min(
                1.0,
                0.80 + (0.05 * min(len(critical_hardware), 4))
            )

            judgments.append(
                Judgment(
                    state="risky",
                    confidence=confidence,
                    evidence=[
                        Evidence(
                            source="windows.event_log",
                            observation=(
                                f"{len(critical_hardware)} critical hardware "
                                "events detected in collected telemetry"
                            ),
                            baseline="No critical hardware events",
                            deviation="Critical hardware events were detected",
                        )
                    ],
                    impact_scope="system-wide",
                    urgency="act-now",
                    recommended_posture="stop",
                )
            )

        elif len(hardware_errors) >= 2:
            confidence = min(
                1.0,
                0.70 + (0.04 * min(len(hardware_errors), 7))
            )

            judgments.append(
                Judgment(
                    state="constrained",
                    confidence=confidence,
                    evidence=[
                        Evidence(
                            source="windows.event_log",
                            observation=(
                                f"{len(hardware_errors)} hardware error "
                                "events detected in collected telemetry"
                            ),
                            baseline="No hardware error events",
                            deviation="Repeated hardware error events detected",
                        )
                    ],
                    impact_scope="system-wide",
                    urgency="act-soon",
                    recommended_posture="investigate",
                )
            )

        if application_crashes:
            confidence = min(
                1.0,
                0.70 + (0.05 * min(len(application_crashes), 6))
            )

            judgments.append(
                Judgment(
                    state="degraded",
                    confidence=confidence,
                    evidence=[
                        Evidence(
                            source="windows.event_log",
                            observation=(
                                f"{len(application_crashes)} application "
                                "crash events detected"
                            ),
                            baseline="No application crash events",
                            deviation="Application crash events detected",
                        )
                    ],
                    impact_scope="local",
                    urgency="act-soon",
                    recommended_posture="investigate",
                )
            )

    return judgments
