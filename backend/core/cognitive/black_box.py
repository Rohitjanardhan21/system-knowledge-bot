"""
CVIS Black Box Recorder
=======================
Continuously records the last 2 hours of everything.
Like an aircraft black box — always recording, never stops.
When something goes wrong, you can replay exactly what happened.

Includes: reconstruct_timeline() for Failure Timeline Reconstruction feature.
"""
import json
import os
import time
import threading
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class BlackBoxFrame:
    """One frame of recorded system state."""
    timestamp:   float
    cpu:         float
    memory:      float
    disk:        float
    network:     float
    health:      float
    anomaly:     float
    if_score:    float
    vae_score:   float
    lstm_score:  float
    top_process: str    # name of highest CPU process
    top_cpu:     float
    reason:      str    # explain_and_act reason at this moment
    severity:    str


# Metric thresholds that define "crossed into warning territory"
# Used by reconstruct_timeline to find the first crossing of each metric
_INCIDENT_THRESHOLDS = {
    "OOM": [
        ("memory",  75.0, "Memory crossed 75% — pressure beginning"),
        ("memory",  82.0, "Memory reached 82% — significant pressure"),
        ("memory",  90.0, "Memory above 90% — crash imminent"),
        ("anomaly",  0.4, "ML anomaly score elevated — unusual pattern detected"),
        ("anomaly",  0.6, "ML anomaly score high — OOM signature confirmed"),
    ],
    "CRASH": [
        ("cpu",     70.0, "CPU spiked above 70%"),
        ("cpu",     85.0, "CPU above 85% — process under severe stress"),
        ("anomaly",  0.3, "ML anomaly score elevated"),
        ("anomaly",  0.6, "ML anomaly score high — crash signature detected"),
    ],
    "THERMAL": [
        ("cpu",     60.0, "CPU sustained above 60% — thermal load building"),
        ("cpu",     75.0, "CPU above 75% — throttling risk"),
        ("cpu",     85.0, "CPU critically high — thermal throttling active"),
    ],
    "FREEZE": [
        ("disk",    70.0, "Disk I/O elevated"),
        ("disk",    85.0, "Disk usage high — I/O saturation risk"),
        ("cpu",     80.0, "CPU high alongside disk pressure"),
        ("anomaly",  0.4, "ML anomaly score elevated"),
    ],
    "CPU_STRESS": [
        ("cpu",     70.0, "CPU crossed 70%"),
        ("cpu",     85.0, "CPU above 85% — stress confirmed"),
        ("anomaly",  0.4, "Anomaly score elevated"),
    ],
    "DISK_FULL": [
        ("disk",    80.0, "Disk crossed 80%"),
        ("disk",    90.0, "Disk above 90% — near capacity"),
        ("disk",    95.0, "Disk critically full"),
    ],
}

# Fallback thresholds if incident_type not in map above
_DEFAULT_THRESHOLDS = [
    ("cpu",     70.0, "CPU spiked above 70%"),
    ("memory",  75.0, "Memory crossed 75%"),
    ("disk",    80.0, "Disk crossed 80%"),
    ("anomaly",  0.4, "Anomaly score elevated"),
]

_METRIC_LABEL = {
    "cpu":     "CPU",
    "memory":  "Memory",
    "disk":    "Disk",
    "network": "Network I/O",
    "anomaly": "Anomaly score",
}


class BlackBoxRecorder:
    """
    Always-on recorder. Keeps 2 hours of second-by-second data.
    On incident, extracts the relevant window for playback.
    """

    MAX_FRAMES     = 1440    # 2 hours at 1 frame per 5 seconds
    FRAME_INTERVAL = 5       # seconds
    INCIDENT_FILE  = "data/incidents.json"

    def __init__(self):
        self._lock = threading.Lock()
        self._buffer: deque = deque(maxlen=self.MAX_FRAMES)
        self._incidents: list = []
        self._last_frame_time = 0.0
        os.makedirs("data", exist_ok=True)
        self._load_incidents()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, metrics: dict, processes: list, reason: str, severity: str):
        """Record one frame. Call this from the main collector loop."""
        now = time.time()
        if now - self._last_frame_time < self.FRAME_INTERVAL:
            return

        self._last_frame_time = now
        top = processes[0] if processes else {}

        frame = BlackBoxFrame(
            timestamp=now,
            cpu=metrics.get("cpu_percent",    0),
            memory=metrics.get("memory",      0),
            disk=metrics.get("disk_percent",  0),
            network=metrics.get("network_percent", 0),
            health=metrics.get("health_score",100),
            anomaly=metrics.get("ensemble_score", 0),
            if_score=metrics.get("if_score",  0),
            vae_score=metrics.get("vae_score",0),
            lstm_score=metrics.get("lstm_score",0),
            top_process=top.get("name", "—"),
            top_cpu=top.get("cpu", 0),
            reason=reason,
            severity=severity,
        )

        with self._lock:
            self._buffer.append(frame)

    # ------------------------------------------------------------------
    # Incident marking
    # ------------------------------------------------------------------

    def mark_incident(self, incident_type: str, description: str) -> str:
        """
        Mark an incident — extracts surrounding frames for playback.
        Returns incident_id.
        """
        with self._lock:
            frames = list(self._buffer)

        now = time.time()
        incident_id = f"incident_{int(now)}"

        cutoff   = now - 30 * 60
        relevant = [f for f in frames if f.timestamp >= cutoff]

        playback = []
        for frame in relevant:
            age_min = (now - frame.timestamp) / 60
            playback.append({
                "t":        round(frame.timestamp, 1),
                "ago_min":  round(age_min, 1),
                "cpu":      frame.cpu,
                "mem":      frame.memory,
                "disk":     frame.disk,
                "anomaly":  frame.anomaly,
                "process":  frame.top_process,
                "reason":   frame.reason,
                "severity": frame.severity,
            })

        went_wrong_at = self._find_inflection(relevant)

        # Build full timeline using the new reconstruction engine
        timeline = self.reconstruct_timeline(
            incident_time=now,
            incident_type=incident_type,
            frames=relevant,
        )

        incident = {
            "incident_id":    incident_id,
            "type":           incident_type,
            "description":    description,
            "occurred_at":    now,
            "occurred_str":   time.strftime("%b %d %Y at %I:%M %p", time.localtime(now)),
            "went_wrong_at":  went_wrong_at,
            "playback":       playback[-60:],
            "full_playback":  playback,
            "plain_timeline": self._build_plain_timeline(relevant, now),
            "timeline":       timeline,   # NEW: structured reconstruction
        }

        with self._lock:
            self._incidents.append(incident)
            if len(self._incidents) > 50:
                self._incidents = self._incidents[-50:]

        self._save_incidents()
        return incident_id

    # ------------------------------------------------------------------
    # NEW: Failure Timeline Reconstruction
    # ------------------------------------------------------------------

    def reconstruct_timeline(
        self,
        incident_time: float,
        incident_type: str,
        frames: Optional[list] = None,
        window_minutes: int = 120,
    ) -> list:
        """
        Reconstruct a structured timeline of metric crossings leading up
        to an incident.

        Returns a list of dicts ordered from earliest to latest:
          {
            t_minus_mins  — how many minutes before the incident
            time_str      — "03:14 AM"
            event         — plain-English description of what crossed
            metric        — "memory" / "cpu" / etc.
            value         — actual value at crossing
            unit          — "%" or ""
            significance  — "primary" / "supporting"
          }

        Works from a supplied frame list (incident replay) or pulls
        directly from the live buffer.
        """
        if frames is None:
            with self._lock:
                all_frames = list(self._buffer)
            cutoff = incident_time - window_minutes * 60
            frames = [f for f in all_frames if f.timestamp >= cutoff]

        if not frames:
            return []

        thresholds = _INCIDENT_THRESHOLDS.get(incident_type, _DEFAULT_THRESHOLDS)

        timeline = []
        seen_thresholds = set()   # prevent duplicate entries for same crossing

        for frame in frames:
            t_minus = (incident_time - frame.timestamp) / 60

            for metric, threshold, label in thresholds:
                crossing_key = f"{metric}_{threshold}"
                if crossing_key in seen_thresholds:
                    continue

                val = self._get_frame_metric(frame, metric)
                if val >= threshold:
                    seen_thresholds.add(crossing_key)
                    unit = "" if metric == "anomaly" else "%"

                    # First threshold for a metric = primary, subsequent = supporting
                    metric_primary_key = f"primary_{metric}"
                    if metric_primary_key not in seen_thresholds:
                        seen_thresholds.add(metric_primary_key)
                        significance = "primary"
                    else:
                        significance = "supporting"

                    timeline.append({
                        "t_minus_mins": round(t_minus, 1),
                        "time_str":     time.strftime("%I:%M %p", time.localtime(frame.timestamp)),
                        "event":        label,
                        "metric":       metric,
                        "value":        round(val, 1),
                        "unit":         unit,
                        "significance": significance,
                    })

        # Sort: earliest first (highest t_minus first)
        timeline.sort(key=lambda x: x["t_minus_mins"], reverse=True)

        # Add the incident marker at the end
        timeline.append({
            "t_minus_mins": 0,
            "time_str":     time.strftime("%I:%M %p", time.localtime(incident_time)),
            "event":        f"{incident_type} incident recorded",
            "metric":       "incident",
            "value":        None,
            "unit":         "",
            "significance": "incident",
        })

        return timeline

    def get_timeline_for_incident(self, incident_id: str) -> dict:
        """
        Public method — called from main.py for /cognitive/postmortem/{id}.
        Returns the full timeline + contributing factors for an incident.
        If the incident was recorded before this feature shipped,
        reconstructs it from stored playback data.
        """
        with self._lock:
            incident = next(
                (i for i in self._incidents if i["incident_id"] == incident_id),
                None
            )

        if not incident:
            return {"error": "Incident not found", "incident_id": incident_id}

        # If timeline was already built at mark time, return it
        if incident.get("timeline"):
            return {
                "incident_id":   incident_id,
                "type":          incident["type"],
                "occurred_str":  incident["occurred_str"],
                "timeline":      incident["timeline"],
                "went_wrong_at": incident.get("went_wrong_at"),
            }

        # Legacy incident — reconstruct from stored playback
        playback = incident.get("full_playback") or incident.get("playback", [])
        if not playback:
            return {
                "incident_id":  incident_id,
                "type":         incident["type"],
                "occurred_str": incident["occurred_str"],
                "timeline":     [],
                "note":         "No playback data available for this incident.",
            }

        # Convert playback dicts back to a frame-like structure
        pseudo_frames = []
        incident_time = incident["occurred_at"]
        for p in playback:
            pseudo_frames.append(_PlaybackFrame(
                timestamp=p.get("t", 0),
                cpu=p.get("cpu", 0),
                memory=p.get("mem", 0),
                disk=p.get("disk", 0),
                anomaly=p.get("anomaly", 0),
            ))

        timeline = self.reconstruct_timeline(
            incident_time=incident_time,
            incident_type=incident["type"],
            frames=pseudo_frames,
        )

        return {
            "incident_id":   incident_id,
            "type":          incident["type"],
            "occurred_str":  incident["occurred_str"],
            "timeline":      timeline,
            "went_wrong_at": incident.get("went_wrong_at"),
            "note":          "Timeline reconstructed from stored playback.",
        }

    # ------------------------------------------------------------------
    # Existing public methods (unchanged)
    # ------------------------------------------------------------------

    def get_recent_frames(self, minutes: int = 10) -> list:
        with self._lock:
            frames = list(self._buffer)
        cutoff = time.time() - minutes * 60
        return [asdict(f) for f in frames if f.timestamp >= cutoff]

    def get_incident(self, incident_id: str) -> Optional[dict]:
        with self._lock:
            return next(
                (i for i in self._incidents if i["incident_id"] == incident_id),
                None
            )

    def get_incidents(self, limit: int = 10) -> list:
        with self._lock:
            return sorted(
                self._incidents,
                key=lambda x: x["occurred_at"],
                reverse=True
            )[:limit]

    def get_status(self) -> dict:
        with self._lock:
            n = len(self._buffer)
        return {
            "frames_recorded":  n,
            "coverage_minutes": round(n * self.FRAME_INTERVAL / 60, 1),
            "incidents_stored": len(self._incidents),
            "recording":        True,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_frame_metric(self, frame, metric: str) -> float:
        """Safely extract a metric value from a BlackBoxFrame or pseudo-frame."""
        return getattr(frame, metric, 0) or 0.0

    def _find_inflection(self, frames: list) -> Optional[str]:
        """Find when things started going wrong."""
        if len(frames) < 5:
            return None
        for i in range(len(frames) - 5, -1, -1):
            f = frames[i]
            if f.anomaly < 0.3 and f.cpu < 60 and f.memory < 70:
                ts = frames[i + 1].timestamp if i + 1 < len(frames) else frames[-1].timestamp
                return time.strftime("%I:%M %p", time.localtime(ts))
        return None

    def _build_plain_timeline(self, frames: list, incident_time: float) -> list:
        """Build human-readable threshold-crossing timeline (original implementation)."""
        if not frames:
            return []

        timeline  = []
        seen_events = set()

        thresholds = [
            ("memory",  75,  "Memory crossed 75%"),
            ("memory",  85,  "Memory reached 85%"),
            ("memory",  90,  "Memory critical — above 90%"),
            ("cpu",     70,  "CPU spiked above 70%"),
            ("cpu",     85,  "CPU critically high"),
            ("anomaly", 0.3, "AI detected unusual behaviour"),
            ("anomaly", 0.6, "AI flagged high anomaly"),
        ]

        for frame in frames:
            age_min = round((incident_time - frame.timestamp) / 60, 0)
            for key, threshold, label in thresholds:
                val = self._get_frame_metric(frame, key)
                event_key = f"{key}_{threshold}"
                if val >= threshold and event_key not in seen_events:
                    seen_events.add(event_key)
                    timeline.append({
                        "ago_min": int(age_min),
                        "label":   label,
                        "value":   round(val, 1),
                        "time":    time.strftime("%I:%M %p", time.localtime(frame.timestamp)),
                    })

        return sorted(timeline, key=lambda x: x["ago_min"], reverse=True)

    def _save_incidents(self):
        try:
            with open(self.INCIDENT_FILE, "w") as f:
                json.dump(self._incidents, f, indent=2)
        except Exception:
            pass

    def _load_incidents(self):
        try:
            if os.path.exists(self.INCIDENT_FILE):
                with open(self.INCIDENT_FILE) as f:
                    self._incidents = json.load(f)
        except Exception:
            pass


# ------------------------------------------------------------------
# Lightweight pseudo-frame for legacy playback reconstruction
# ------------------------------------------------------------------

class _PlaybackFrame:
    """Duck-typed frame for reconstructing timelines from stored playback dicts."""
    __slots__ = ("timestamp", "cpu", "memory", "disk", "network", "anomaly",
                 "if_score", "vae_score", "lstm_score",
                 "top_process", "top_cpu", "reason", "severity")

    def __init__(self, timestamp=0, cpu=0, memory=0, disk=0,
                 network=0, anomaly=0):
        self.timestamp   = timestamp
        self.cpu         = cpu
        self.memory      = memory
        self.disk        = disk
        self.network     = network
        self.anomaly     = anomaly
        self.if_score    = 0.0
        self.vae_score   = 0.0
        self.lstm_score  = 0.0
        self.top_process = "—"
        self.top_cpu     = 0.0
        self.reason      = ""
        self.severity    = ""


# ── Singleton ─────────────────────────────────────────────

_black_box: Optional[BlackBoxRecorder] = None
_bb_lock = threading.Lock()

def get_black_box() -> BlackBoxRecorder:
    global _black_box
    with _bb_lock:
        if _black_box is None:
            _black_box = BlackBoxRecorder()
    return _black_box
