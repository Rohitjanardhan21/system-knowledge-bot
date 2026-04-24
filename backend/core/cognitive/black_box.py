"""
CVIS Black Box Recorder
=======================
Continuously records the last 2 hours of everything.
Like an aircraft black box — always recording, never stops.
When something goes wrong, you can replay exactly what happened.
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


class BlackBoxRecorder:
    """
    Always-on recorder. Keeps 2 hours of second-by-second data.
    On incident, extracts the relevant window for playback.
    """

    # 2 hours at 1 frame per 5 seconds = 1440 frames
    MAX_FRAMES = 1440
    FRAME_INTERVAL = 5   # seconds

    INCIDENT_FILE = "data/incidents.json"

    def __init__(self):
        self._lock = threading.Lock()
        self._buffer: deque = deque(maxlen=self.MAX_FRAMES)
        self._incidents: list = []
        self._last_frame_time = 0.0
        os.makedirs("data", exist_ok=True)
        self._load_incidents()

    def record(self, metrics: dict, processes: list, reason: str, severity: str):
        """Record one frame. Call this from the main collector loop."""
        now = time.time()
        if now - self._last_frame_time < self.FRAME_INTERVAL:
            return

        self._last_frame_time = now
        top = processes[0] if processes else {}

        frame = BlackBoxFrame(
            timestamp=now,
            cpu=metrics.get("cpu_percent", 0),
            memory=metrics.get("memory", 0),
            disk=metrics.get("disk_percent", 0),
            network=metrics.get("network_percent", 0),
            health=metrics.get("health_score", 100),
            anomaly=metrics.get("ensemble_score", 0),
            if_score=metrics.get("if_score", 0),
            vae_score=metrics.get("vae_score", 0),
            lstm_score=metrics.get("lstm_score", 0),
            top_process=top.get("name", "—"),
            top_cpu=top.get("cpu", 0),
            reason=reason,
            severity=severity,
        )

        with self._lock:
            self._buffer.append(frame)

    def mark_incident(self, incident_type: str, description: str) -> str:
        """
        Mark an incident — extracts surrounding frames for playback.
        Returns incident_id.
        """
        with self._lock:
            frames = list(self._buffer)

        now = time.time()
        incident_id = f"incident_{int(now)}"

        # Extract frames from 30 minutes before to now
        cutoff = now - 30 * 60
        relevant = [f for f in frames if f.timestamp >= cutoff]

        # Build playback data
        playback = []
        for frame in relevant:
            age_min = (now - frame.timestamp) / 60
            playback.append({
                "t":       round(frame.timestamp, 1),
                "ago_min": round(age_min, 1),
                "cpu":     frame.cpu,
                "mem":     frame.memory,
                "disk":    frame.disk,
                "anomaly": frame.anomaly,
                "process": frame.top_process,
                "reason":  frame.reason,
                "severity": frame.severity,
            })

        # Find the point things went wrong
        went_wrong_at = self._find_inflection(relevant)

        incident = {
            "incident_id":   incident_id,
            "type":          incident_type,
            "description":   description,
            "occurred_at":   now,
            "occurred_str":  time.strftime("%b %d %Y at %I:%M %p", time.localtime(now)),
            "went_wrong_at": went_wrong_at,
            "playback":      playback[-60:],   # last 60 frames (5 min)
            "full_playback": playback,
            "plain_timeline": self._build_plain_timeline(relevant, now),
        }

        with self._lock:
            self._incidents.append(incident)
            # Keep last 50 incidents
            if len(self._incidents) > 50:
                self._incidents = self._incidents[-50:]

        self._save_incidents()
        return incident_id

    def get_recent_frames(self, minutes: int = 10) -> list:
        """Get recent frames for live playback."""
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
            "frames_recorded": n,
            "coverage_minutes": round(n * self.FRAME_INTERVAL / 60, 1),
            "incidents_stored": len(self._incidents),
            "recording": True,
        }

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
        """Build human-readable timeline of events leading to incident."""
        if not frames:
            return []

        timeline = []
        seen_events = set()

        # Check key thresholds over time
        thresholds = [
            ("memory",  75, "Memory crossed 75%"),
            ("memory",  85, "Memory reached 85%"),
            ("memory",  90, "Memory critical — above 90%"),
            ("cpu",     70, "CPU spiked above 70%"),
            ("cpu",     85, "CPU critically high"),
            ("anomaly", 0.3, "AI detected unusual behaviour"),
            ("anomaly", 0.6, "AI flagged high anomaly"),
        ]

        for frame in frames:
            age_min = round((incident_time - frame.timestamp) / 60, 0)
            for key, threshold, label in thresholds:
                val = getattr(frame, key if key != "memory" else "memory", 0)
                if key == "memory":
                    val = frame.memory
                elif key == "cpu":
                    val = frame.cpu
                elif key == "anomaly":
                    val = frame.anomaly

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


# ── Singleton ─────────────────────────────────────────────
_black_box: Optional[BlackBoxRecorder] = None
_bb_lock = threading.Lock()

def get_black_box() -> BlackBoxRecorder:
    global _black_box
    with _bb_lock:
        if _black_box is None:
            _black_box = BlackBoxRecorder()
    return _black_box
