"""
CVIS Post-Mortem Builder
========================
Takes raw incident data + reconstructed timeline from the Black Box
and produces a complete, plain-English post-mortem report.

This is the second half of the Failure Timeline Reconstruction feature.
black_box.py finds WHAT happened and WHEN.
postmortem_builder.py explains WHY and WHAT TO DO NEXT.

Used by: GET /cognitive/postmortem/{id}
"""
import time
from typing import Optional


# ------------------------------------------------------------------
# Contributing factor classification
# ------------------------------------------------------------------

_FACTOR_RULES = {
    "OOM": [
        {
            "metric":   "memory",
            "threshold": 82.0,
            "impact":   "primary",
            "detail_fn": lambda v: (
                f"RAM was at {v:.0f}% — sustained memory pressure "
                f"above 80% is the direct cause of OOM events."
            ),
        },
        {
            "metric":   "memory",
            "threshold": 75.0,
            "impact":   "accelerant",
            "detail_fn": lambda v: (
                f"Memory reached {v:.0f}% before the final spike — "
                f"the system had no headroom left to absorb the final load."
            ),
        },
        {
            "metric":   "cpu",
            "threshold": 70.0,
            "impact":   "secondary",
            "detail_fn": lambda v: (
                f"CPU was also elevated at {v:.0f}% — concurrent CPU pressure "
                f"reduces the kernel's ability to reclaim memory pages."
            ),
        },
        {
            "metric":   "anomaly",
            "threshold": 0.4,
            "impact":   "supporting",
            "detail_fn": lambda v: (
                f"ML anomaly score reached {v:.2f} — the pattern matched "
                f"historical OOM signatures in your failure DNA."
            ),
        },
    ],
    "CRASH": [
        {
            "metric":   "cpu",
            "threshold": 80.0,
            "impact":   "primary",
            "detail_fn": lambda v: (
                f"CPU reached {v:.0f}% — the process likely ran out of "
                f"scheduling headroom and terminated abnormally."
            ),
        },
        {
            "metric":   "anomaly",
            "threshold": 0.5,
            "impact":   "accelerant",
            "detail_fn": lambda v: (
                f"Anomaly score hit {v:.2f} — the ML model detected "
                f"the signature pattern that precedes crashes on this machine."
            ),
        },
        {
            "metric":   "memory",
            "threshold": 75.0,
            "impact":   "secondary",
            "detail_fn": lambda v: (
                f"Memory was at {v:.0f}% — memory pressure may have "
                f"contributed to the instability."
            ),
        },
    ],
    "THERMAL": [
        {
            "metric":   "cpu",
            "threshold": 75.0,
            "impact":   "primary",
            "detail_fn": lambda v: (
                f"CPU sustained at {v:.0f}% — prolonged high CPU is "
                f"the direct driver of thermal throttling."
            ),
        },
        {
            "metric":   "cpu",
            "threshold": 60.0,
            "impact":   "accelerant",
            "detail_fn": lambda v: (
                f"CPU was above 60% for an extended period before "
                f"reaching critical levels — heat accumulated over time."
            ),
        },
    ],
    "FREEZE": [
        {
            "metric":   "disk",
            "threshold": 80.0,
            "impact":   "primary",
            "detail_fn": lambda v: (
                f"Disk usage was at {v:.0f}% — I/O saturation at high "
                f"disk usage is a common freeze trigger."
            ),
        },
        {
            "metric":   "cpu",
            "threshold": 75.0,
            "impact":   "accelerant",
            "detail_fn": lambda v: (
                f"CPU was also at {v:.0f}% — combined CPU and disk "
                f"pressure exhausted the system's I/O queue."
            ),
        },
        {
            "metric":   "anomaly",
            "threshold": 0.4,
            "impact":   "supporting",
            "detail_fn": lambda v: (
                f"Anomaly score reached {v:.2f} — unusual I/O pattern "
                f"detected before the freeze."
            ),
        },
    ],
    "CPU_STRESS": [
        {
            "metric":   "cpu",
            "threshold": 85.0,
            "impact":   "primary",
            "detail_fn": lambda v: (
                f"CPU reached {v:.0f}% — the workload exceeded safe "
                f"operating capacity for sustained periods."
            ),
        },
        {
            "metric":   "anomaly",
            "threshold": 0.4,
            "impact":   "supporting",
            "detail_fn": lambda v: (
                f"Anomaly score elevated to {v:.2f} — abnormal CPU "
                f"pattern confirmed by ML models."
            ),
        },
    ],
    "DISK_FULL": [
        {
            "metric":   "disk",
            "threshold": 90.0,
            "impact":   "primary",
            "detail_fn": lambda v: (
                f"Disk reached {v:.0f}% — writes begin failing once "
                f"disk hits 95%, causing application errors."
            ),
        },
        {
            "metric":   "disk",
            "threshold": 80.0,
            "impact":   "accelerant",
            "detail_fn": lambda v: (
                f"Disk was already at {v:.0f}% before the event — "
                f"there was insufficient headroom for growth."
            ),
        },
    ],
}

_DEFAULT_FACTOR_RULES = [
    {
        "metric":    "cpu",
        "threshold": 75.0,
        "impact":    "primary",
        "detail_fn": lambda v: f"CPU reached {v:.0f}% — elevated workload contributed to the event.",
    },
    {
        "metric":    "memory",
        "threshold": 78.0,
        "impact":    "primary",
        "detail_fn": lambda v: f"Memory was at {v:.0f}% — pressure may have triggered the event.",
    },
    {
        "metric":    "anomaly",
        "threshold": 0.4,
        "impact":    "supporting",
        "detail_fn": lambda v: f"ML anomaly score was {v:.2f} — unusual behaviour detected.",
    },
]

# ------------------------------------------------------------------
# What-to-watch rules per incident type
# ------------------------------------------------------------------

_WHAT_TO_WATCH = {
    "OOM": [
        "RAM usage above 75% sustained for 10+ minutes — close unused apps immediately",
        "Swap usage growing faster than 5% per minute — indicates memory pages being pushed out",
        "Any single process consuming more than 40% RAM — identify and restart if safe",
    ],
    "CRASH": [
        "CPU above 80% for more than 5 consecutive minutes — check for runaway processes",
        "Anomaly score rising above 0.5 — the ML model is seeing a pre-crash pattern",
        "Application logs for the crashed process — look for out-of-memory or segfault entries",
    ],
    "THERMAL": [
        "CPU above 60% sustained for 30+ minutes — ensure adequate cooling and airflow",
        "Performance degradation (slower responses, lag) — early sign of throttling",
        "Physical temperature if accessible — consider a cooling pad or environment check",
    ],
    "FREEZE": [
        "Disk I/O wait times — high wait = I/O queue saturated",
        "Available disk space — ensure at least 15% free at all times",
        "CPU + Disk simultaneously high — this combination frequently precedes freezes",
    ],
    "CPU_STRESS": [
        "Processes with consistently high CPU — use CVIS one-click to identify and act",
        "CPU above 85% for more than 2 minutes — consider distributing load",
        "Anomaly score — if it spikes alongside CPU, a crash may follow",
    ],
    "DISK_FULL": [
        "Disk usage above 85% — run CVIS disk cleanup or clear logs",
        "Disk growth rate — if growing more than 1GB/day, identify the source",
        "Application write errors in logs — these appear before disk is completely full",
    ],
}

_DEFAULT_WHAT_TO_WATCH = [
    "System anomaly score — rising score means ML models are detecting unusual patterns",
    "The metric that spiked first — monitor it closely over the next 24 hours",
]

# ------------------------------------------------------------------
# Recommendations per incident type
# ------------------------------------------------------------------

_RECOMMENDATIONS = {
    "OOM": (
        "Add more RAM or reduce concurrent workload. "
        "Close memory-heavy applications during intensive sessions. "
        "Consider setting memory limits on individual processes."
    ),
    "CRASH": (
        "Check application logs for the crashed process. "
        "Update the software if a newer version is available. "
        "If crash recurs, consider isolating the process in a container."
    ),
    "THERMAL": (
        "Clean cooling vents and ensure adequate airflow around the machine. "
        "Reduce sustained CPU workloads or schedule heavy tasks with breaks. "
        "Consider a cooling pad if this is a laptop."
    ),
    "FREEZE": (
        "Restart to clear accumulated I/O state. "
        "Check disk health with a SMART scan. "
        "Ensure at least 15% free disk space is maintained at all times."
    ),
    "CPU_STRESS": (
        "Identify the process driving CPU and determine if it is expected workload. "
        "Distribute tasks across time rather than running simultaneously. "
        "Consider hardware upgrade if this is a recurring pattern."
    ),
    "DISK_FULL": (
        "Run disk cleanup — remove old logs, temp files, and unused Docker images. "
        "Set up automated log rotation if not already in place. "
        "Add disk space monitoring alerts at 80% and 90%."
    ),
}

_DEFAULT_RECOMMENDATION = (
    "Review the timeline above to identify the root cause. "
    "Monitor the system closely over the next 24 hours. "
    "Use CVIS one-click actions to address the most elevated metric."
)


# ------------------------------------------------------------------
# Builder
# ------------------------------------------------------------------

class PostMortemBuilder:
    """
    Builds a complete plain-English post-mortem from incident data.

    Input:  incident dict from black_box + reconstructed timeline
    Output: structured post-mortem with factors, what-to-watch, recommendation
    """

    def build(
        self,
        incident: dict,
        timeline: list,
        peak_metrics: Optional[dict] = None,
    ) -> dict:
        """
        Build a full post-mortem report.

        Args:
            incident     — incident dict from BlackBoxRecorder
            timeline     — output of reconstruct_timeline()
            peak_metrics — optional dict of {metric: peak_value} seen in playback.
                           If not supplied, peaks are extracted from the timeline.

        Returns:
            Full post-mortem dict ready to be returned by /cognitive/postmortem/{id}
        """
        incident_type = incident.get("type", "UNKNOWN")
        occurred_str  = incident.get("occurred_str", "Unknown time")
        description   = incident.get("description", "")

        # Extract peak values from timeline if not supplied
        if peak_metrics is None:
            peak_metrics = self._extract_peaks(timeline)

        # Build contributing factors
        factors = self._build_factors(incident_type, peak_metrics)

        # What to watch
        what_to_watch = _WHAT_TO_WATCH.get(incident_type, _DEFAULT_WHAT_TO_WATCH)

        # Recommendation
        recommendation = _RECOMMENDATIONS.get(incident_type, _DEFAULT_RECOMMENDATION)

        # Plain summary of what happened
        what_happened = self._build_what_happened(incident_type, occurred_str, peak_metrics)

        # Time from first warning to incident
        lead_time = self._calc_lead_time(timeline)

        # Was CVIS watching? (did it have data before the event)
        cvis_coverage = self._assess_cvis_coverage(timeline, incident)

        return {
            "incident_id":     incident.get("incident_id"),
            "type":            incident_type,
            "occurred_at":     occurred_str,
            "description":     description,
            "what_happened":   what_happened,
            "timeline":        timeline,
            "contributing_factors": factors,
            "what_to_watch":   what_to_watch[:3],
            "recommendation":  recommendation,
            "lead_time_mins":  lead_time,
            "lead_time_str":   f"{lead_time} minutes" if lead_time else "Insufficient data",
            "cvis_coverage":   cvis_coverage,
            "generated_at":    time.strftime("%b %d, %Y at %I:%M %p"),
        }

    # ------------------------------------------------------------------
    # Private: Contributing factors
    # ------------------------------------------------------------------

    def _build_factors(self, incident_type: str, peak_metrics: dict) -> list:
        """
        Match peak metric values against factor rules to produce
        a ranked list of contributing factors.
        """
        rules   = _FACTOR_RULES.get(incident_type, _DEFAULT_FACTOR_RULES)
        factors = []
        seen_impacts = set()

        for rule in rules:
            metric    = rule["metric"]
            threshold = rule["threshold"]
            impact    = rule["impact"]
            detail_fn = rule["detail_fn"]

            peak_val = peak_metrics.get(metric, 0)
            if peak_val >= threshold:
                # Only one "primary" factor — promote to supporting if already filled
                if impact == "primary" and "primary" in seen_impacts:
                    impact = "supporting"

                seen_impacts.add(impact)

                factors.append({
                    "factor":    _METRIC_FACTOR_NAME.get(metric, metric.capitalize()),
                    "impact":    impact,
                    "peak":      round(peak_val, 1),
                    "unit":      "" if metric == "anomaly" else "%",
                    "detail":    detail_fn(peak_val),
                })

        if not factors:
            factors.append({
                "factor":  "System stress",
                "impact":  "primary",
                "peak":    None,
                "unit":    "",
                "detail":  "Insufficient metric data to identify a specific contributing factor.",
            })

        return factors

    # ------------------------------------------------------------------
    # Private: Peak extraction from timeline
    # ------------------------------------------------------------------

    def _extract_peaks(self, timeline: list) -> dict:
        """
        Scan the timeline to find the peak value seen for each metric.
        Falls back to 0 for any metric not present.
        """
        peaks: dict = {}
        for entry in timeline:
            metric = entry.get("metric")
            value  = entry.get("value")
            if metric and value is not None and metric != "incident":
                peaks[metric] = max(peaks.get(metric, 0), value)
        return peaks

    # ------------------------------------------------------------------
    # Private: Lead time calculation
    # ------------------------------------------------------------------

    def _calc_lead_time(self, timeline: list) -> Optional[int]:
        """
        Calculate the gap between the first warning event and the incident.
        Returns minutes, or None if no timeline data.
        """
        non_incident = [
            e for e in timeline
            if e.get("significance") != "incident" and e.get("t_minus_mins", 0) > 0
        ]
        if not non_incident:
            return None
        # Earliest event = largest t_minus_mins
        earliest = max(non_incident, key=lambda x: x.get("t_minus_mins", 0))
        return int(earliest.get("t_minus_mins", 0))

    # ------------------------------------------------------------------
    # Private: CVIS coverage assessment
    # ------------------------------------------------------------------

    def _assess_cvis_coverage(self, timeline: list, incident: dict) -> dict:
        """
        Report whether CVIS had monitoring data before the incident,
        and whether it fired any alerts.
        """
        non_incident = [e for e in timeline if e.get("significance") != "incident"]
        had_data = len(non_incident) > 0

        # Check if CVIS raised severity in playback
        playback = incident.get("playback") or incident.get("full_playback", [])
        cvis_alerted = any(
            p.get("severity") in ("HIGH", "CRITICAL") for p in playback
        )

        if not had_data:
            note = "CVIS did not have pre-incident monitoring data for this event."
        elif cvis_alerted:
            note = "CVIS detected elevated severity before the incident occurred."
        else:
            note = "CVIS was recording but did not reach HIGH/CRITICAL alert threshold before the incident."

        return {
            "had_data":     had_data,
            "cvis_alerted": cvis_alerted,
            "note":         note,
        }

    # ------------------------------------------------------------------
    # Private: What happened summary
    # ------------------------------------------------------------------

    def _build_what_happened(
        self, incident_type: str, occurred_str: str, peak_metrics: dict
    ) -> str:
        base = {
            "OOM": (
                "The system ran out of available memory. "
                f"RAM peaked at {peak_metrics.get('memory', '?'):.0f}% before the event."
            ),
            "CRASH": (
                "A process terminated unexpectedly. "
                f"CPU reached {peak_metrics.get('cpu', '?'):.0f}% in the lead-up."
            ),
            "THERMAL": (
                "The CPU overheated, causing performance throttling. "
                f"CPU was sustained at {peak_metrics.get('cpu', '?'):.0f}%."
            ),
            "FREEZE": (
                "The system became unresponsive, likely due to I/O saturation. "
                f"Disk was at {peak_metrics.get('disk', '?'):.0f}% and CPU at "
                f"{peak_metrics.get('cpu', '?'):.0f}%."
            ),
            "CPU_STRESS": (
                f"CPU stress reached {peak_metrics.get('cpu', '?'):.0f}%, "
                "exceeding safe operating limits."
            ),
            "DISK_FULL": (
                f"Disk usage reached {peak_metrics.get('disk', '?'):.0f}%, "
                "causing write failures and application errors."
            ),
        }.get(incident_type)

        if not base:
            base = f"An incident of type {incident_type} occurred at {occurred_str}."

        return base


# ------------------------------------------------------------------
# Metric display names for factors
# ------------------------------------------------------------------

_METRIC_FACTOR_NAME = {
    "cpu":     "CPU pressure",
    "memory":  "Memory pressure",
    "disk":    "Disk usage",
    "network": "Network I/O",
    "anomaly": "ML anomaly signal",
}


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_builder: Optional[PostMortemBuilder] = None

def get_postmortem_builder() -> PostMortemBuilder:
    global _builder
    if _builder is None:
        _builder = PostMortemBuilder()
    return _builder
