from .store import create_alert


def forecast_risk(memory_pct):

    if memory_pct > 90:
        return create_alert(
            "critical",
            "forecast",
            "Memory exhaustion imminent"
        )

    if memory_pct > 80:
        return create_alert(
            "warning",
            "forecast",
            "Memory pressure rising"
        )


def collector_failed():

    return create_alert(
        "critical",
        "collector",
        "System telemetry collector failed"
    )
