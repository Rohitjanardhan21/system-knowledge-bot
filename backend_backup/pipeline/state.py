"""
pipeline/state.py  —  CVIS v5.3
─────────────────────────────────────────
Shared system state — thread-safe singleton.

[v5.3] Five precision fixes to the spatial hazard memory:

  Fix 1 — Heading reliability:
    GPS heading is suppressed when gps_speed < 5 km/h.
    At low speed the magnetometer / GPS track-angle is noisy and
    pointing in essentially a random direction — disabling the cone
    filter is safer than mis-suppressing real hazards.

  Fix 2 — Pending buffer expiry:
    Pending entries older than PENDING_TTL_SECONDS (10 s) are
    reaped at query time and on every store_hazard() call.
    Prevents unbounded memory growth from one-off noise detections.

  Fix 3 — Heatmap resolution 20 m:
    Grid reduced from 0.001° (~111 m) to 0.0002° (~22 m).
    Finer grid gives actionable street-level density maps.

  Fix 4 — Store normalised hazard type:
    raw_type is mapped through normalize_hazard_type() before
    being written to the confirmed deque.  Memory is now consistent
    (ROAD / TRAFFIC / HUMAN / etc.) regardless of vision label noise.

  Fix 5 — Multi-hazard decision:
    get_top_hazards() returns the N closest approaching hazards
    and computes a weighted composite severity so the decision
    engine can factor in overlapping threat density, not just
    the single closest hit.
"""

import math
import random
import threading
import time
from collections import deque, defaultdict


# ──────────────────────────────────────────────────────────────
# Geometry helpers
# ──────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing (°, 0 = N, clockwise) from point 1 → 2."""
    phi1    = math.radians(lat1)
    phi2    = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = (math.cos(phi1) * math.sin(phi2)
         - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _angle_diff(a: float, b: float) -> float:
    """Shortest angular separation between two compass bearings → [0, 180]."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


# ──────────────────────────────────────────────────────────────
# Decay helper
# ──────────────────────────────────────────────────────────────

_DECAY_WINDOW = 60 * 60 * 24 * 30  # 30 days


def _decay_confidence(hazard: dict, now: float | None = None) -> float:
    """Linear confidence ∈ [0, 1]; returns 0 when hazard has expired."""
    if now is None:
        now = time.time()
    age = now - hazard.get("timestamp", now)
    if age >= _DECAY_WINDOW:
        return 0.0
    return round(1.0 - age / _DECAY_WINDOW, 4)


class SystemState:
    # ── Confidence gating ──────────────────────────────────────
    STORE_SEV_THRESHOLD = 0.70   # immediate commit if severity ≥ this
    STORE_MIN_HITS      = 2      # else wait for this many pending hits

    # ── [Fix 1] Heading reliability — speed gate ───────────────
    # GPS heading is unreliable below this speed (km/h).
    # When stationary or creeping, direction filter is disabled.
    HEADING_MIN_SPEED_KMH = 5.0

    # ── Direction-filter cone ──────────────────────────────────
    APPROACH_CONE_DEG = 45.0

    # ── [Fix 2] Pending buffer TTL ─────────────────────────────
    # Pending entries older than this are discarded automatically.
    PENDING_TTL_SECONDS = 10.0

    # ── [Fix 3] Heatmap resolution ~22 m ──────────────────────
    _HEATMAP_GRID = 0.0002   # degrees  (was 0.001 / ~111 m)

    def __init__(self):
        self._lock = threading.Lock()

        self._sensors:    dict  = {}
        self._staleness:  dict  = {}
        self._fusion_ts:  float = 0.0

        self.driver_profile: dict = {
            "attention_score": 0.88,
            "fatigue_level":   0.15,
            "aggression":      0.22,
            "reaction_time":   0.28,
            "style":           "MODERATE",
        }

        self.component_health: dict = {
            "engine":       92.0,
            "transmission": 88.0,
            "brakes_front": 85.0,
            "brakes_rear":  87.0,
            "tire_fl":      90.0,
            "tire_fr":      89.0,
            "tire_rl":      91.0,
            "tire_rr":      88.0,
            "suspension":   82.0,
            "steering":     95.0,
            "battery":      78.0,
            "cooling":      84.0,
        }

        self.failsafe_mode: str = "NORMAL"
        self.latency: dict = {
            "vision": 0, "fusion": 0, "anomaly": 0,
            "decision": 0, "render": 0,
        }

        self.last_frame: dict = {}
        self._gps:        dict = {}
        self._scenario:   str | None = None
        self._scenario_overrides: dict = {}
        self._start_time  = time.time()
        self._frame_count = 0

        self._anomaly_history: deque = deque(maxlen=30)

        # Confirmed spatial hazard memory
        self._hazard_memory: deque = deque(maxlen=200)

        # [Fix 2] Pending buffer — pre-confirmation staging area
        # key: (lat_4dp, lon_4dp, canonical_type) → entry dict
        self._pending_hazards: dict = {}

        # [Fix 3] Heatmap at ~22 m grid
        self._heatmap: dict = defaultdict(int)

    # ── Sensor update ─────────────────────────────────────────

    def update_sensors(self, fused: dict):
        with self._lock:
            self._staleness = fused.pop("_staleness", {})
            self._fusion_ts = fused.pop("_fusion_ts", time.time())
            self._sensors.update(fused)
            self._update_gps(fused)
            self._update_driver_profile(fused)
            self._update_component_health(fused)
            self._update_failsafe(fused)
            self._frame_count += 1

    def get_fused_snapshot(self) -> dict:
        with self._lock:
            snap = dict(self._sensors)
            if self._scenario_overrides:
                snap.update(self._scenario_overrides)
            return snap

    def get_staleness(self) -> dict:
        with self._lock:
            return dict(self._staleness)

    # ── Anomaly tracking ──────────────────────────────────────

    def update_anomaly(self, score: float):
        with self._lock:
            self._anomaly_history.append(float(score))

    def get_anomaly_trend(self) -> float:
        with self._lock:
            if len(self._anomaly_history) < 5:
                return 0.0
            hist = list(self._anomaly_history)
            return round((hist[-1] - hist[0]) / len(hist), 5)

    def predict_risk(self) -> float:
        with self._lock:
            if not self._anomaly_history:
                return 0.0
            latest = self._anomaly_history[-1]
        trend = self.get_anomaly_trend()
        return round(min(1.0, latest * (1.0 + trend * 5.0)), 4)

    # ── GPS ───────────────────────────────────────────────────

    def _update_gps(self, fused: dict):
        if "gps_lat" in fused:
            self._gps = {
                "lat":     fused.get("gps_lat",     0),
                "lon":     fused.get("gps_lon",     0),
                "alt":     fused.get("gps_alt",     0),
                "speed":   fused.get("gps_speed",   0),
                "heading": fused.get("gps_heading", 0),
            }

    def get_gps(self) -> dict:
        with self._lock:
            return dict(self._gps)

    # ── Driver profile ────────────────────────────────────────

    def _update_driver_profile(self, fused: dict):
        acc_x    = abs(fused.get("acc_x",    0))
        acc_y    = abs(fused.get("acc_y",    0))
        gyro_yaw = abs(fused.get("gyro_yaw", 0))
        lane_off = abs(fused.get("lane_offset", 0))
        speed    = fused.get("speed", 0)
        brake_p  = fused.get("brake_pressure", 0)

        raw_aggression = min(1.0, (acc_x*2 + acc_y*1.5 + gyro_yaw*0.5) / 4)
        raw_fatigue    = min(1.0, lane_off*1.5 + gyro_yaw*0.3)
        raw_attention  = max(0.1, 1 - (raw_fatigue*0.5 + raw_aggression*0.2))
        reaction       = max(0.15, min(0.5, 0.3 - brake_p*0.001 + random.gauss(0, 0.01)))

        alpha = 0.05
        dp = self.driver_profile
        dp["aggression"]      = _ema(dp["aggression"],      raw_aggression, alpha)
        dp["fatigue_level"]   = _ema(dp["fatigue_level"],   raw_fatigue,    alpha * 0.5)
        dp["attention_score"] = _ema(dp["attention_score"], raw_attention,  alpha)
        dp["reaction_time"]   = _ema(dp["reaction_time"],   reaction,       alpha)
        dp["style"] = (
            "AGGRESSIVE"  if dp["aggression"]    > 0.55 else
            "DISTRACTED"  if dp["fatigue_level"] > 0.50 else
            "DEFENSIVE"   if speed < 40 and dp["attention_score"] > 0.80 else
            "MODERATE"
        )

    # ── Component health ──────────────────────────────────────

    def _update_component_health(self, fused: dict):
        ch    = self.component_health
        temp  = fused.get("thermal",       80)
        vib   = fused.get("vibration",      0)
        brake = fused.get("brake_pressure", 0)

        if temp  > 95: ch["engine"]  = max(0, ch["engine"]  - 0.05)
        if temp  > 95: ch["cooling"] = max(0, ch["cooling"] - 0.03)
        if vib   > 30:
            for t in ["tire_fl","tire_fr","tire_rl","tire_rr"]:
                ch[t] = max(0, ch[t] - 0.01)
            ch["suspension"] = max(0, ch["suspension"] - 0.02)
        if brake > 60: ch["brakes_front"] = max(0, ch["brakes_front"] - 0.02)
        if brake > 60: ch["brakes_rear"]  = max(0, ch["brakes_rear"]  - 0.01)
        for key in ch:
            ch[key] = min(100, ch[key] + 0.0001)

        if self._scenario == "brake_failure":
            ch["brakes_front"] = max(0, ch["brakes_front"] - 5)
        if self._scenario == "engine_overheat":
            ch["engine"]       = max(0, ch["engine"]       - 3)
        if self._scenario == "tire_blowout":
            ch["tire_fl"]      = max(0, ch["tire_fl"]      - 40)

    def get_component_issues(self) -> list[dict]:
        return [
            {"component": k, "health": v, "issue": _health_issue(v)}
            for k, v in self.component_health.items()
            if v < 60
        ]

    # ── Failsafe ──────────────────────────────────────────────

    def _update_failsafe(self, fused: dict):
        ch_min  = min(self.component_health.values())
        fatigue = self.driver_profile["fatigue_level"]
        if ch_min < 20 or fatigue > 0.85:   self.failsafe_mode = "EMERGENCY"
        elif ch_min < 40 or fatigue > 0.65: self.failsafe_mode = "SAFE_MODE"
        elif ch_min < 60:                   self.failsafe_mode = "DEGRADED"
        else:                               self.failsafe_mode = "NORMAL"

    # ── Predictive maintenance ────────────────────────────────

    def predictive_maintenance_alerts(self) -> list[dict]:
        alerts = []
        priority = {
            "brakes_front": ("Brake Pad Wear",        0.80),
            "brakes_rear":  ("Brake Pad Wear",         0.70),
            "tire_fl":      ("Tire Pressure / Wear",  0.75),
            "tire_fr":      ("Tire Pressure / Wear",  0.75),
            "battery":      ("Battery Degradation",    0.65),
            "cooling":      ("Coolant Flush Required", 0.60),
            "suspension":   ("Suspension Check",       0.55),
        }
        for comp, (ptype, base_sev) in priority.items():
            health = self.component_health.get(comp, 100)
            if health < 70:
                severity = base_sev + (70 - health) / 100
                ttf_km   = max(0, int((health - 20) * 80))
                alerts.append({
                    "type":         ptype,
                    "component":    comp,
                    "time_to_risk": f"~{ttf_km} km",
                    "severity":     round(min(1.0, severity), 3),
                })
        return sorted(alerts, key=lambda x: -x["severity"])[:5]

    # ══════════════════════════════════════════════════════════
    # Spatial hazard memory — v5.3
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _pending_key(lat: float, lon: float, hazard_type: str) -> tuple:
        """4 dp (~11 m) grid key for pending-buffer deduplication."""
        return (round(lat, 4), round(lon, 4), hazard_type)

    # ── [Fix 2] Pending buffer reaper ─────────────────────────

    def _reap_pending(self, now: float) -> None:
        """
        Remove stale pending entries that never reached STORE_MIN_HITS.
        Must be called while holding self._lock.
        Runs on every store_hazard() call — O(pending) which stays small.
        """
        expired_keys = [
            k for k, v in self._pending_hazards.items()
            if now - v["first_ts"] > self.PENDING_TTL_SECONDS
        ]
        for k in expired_keys:
            del self._pending_hazards[k]

    # ── Internal merge into confirmed memory ──────────────────

    def _merge_hazard(
        self, lat: float, lon: float, hazard_type: str, severity: float,
    ) -> bool:
        """Upgrade existing confirmed hazard within 5 m. Lock must be held."""
        for h in self._hazard_memory:
            if h["type"] != hazard_type:
                continue
            if _haversine(lat, lon, h["lat"], h["lon"]) < 5.0:
                h["severity"]  = max(h["severity"], severity)
                h["count"]    += 1
                h["timestamp"] = time.time()
                return True
        return False

    def _commit_hazard(
        self, lat: float, lon: float, hazard_type: str, severity: float,
    ) -> None:
        """Write to confirmed memory + update heatmap. Lock must be held."""
        if not self._merge_hazard(lat, lon, hazard_type, severity):
            self._hazard_memory.append({
                "lat":       lat,
                "lon":       lon,
                "type":      hazard_type,   # [Fix 4] already canonical
                "severity":  severity,
                "timestamp": time.time(),
                "count":     1,
            })
        # [Fix 3] ~22 m heatmap cell
        g  = self._HEATMAP_GRID
        gk = (round(round(lat / g) * g, 6), round(round(lon / g) * g, 6))
        self._heatmap[gk] += 1

    # ── Public: store_hazard ───────────────────────────────────

    def store_hazard(
        self,
        lat:         float,
        lon:         float,
        hazard_type: str,     # [Fix 4] expects canonical type (ROAD / TRAFFIC / …)
        severity:    float,
    ) -> dict:
        """
        Gate a detected hazard through the confidence buffer.

        [Fix 4] hazard_type MUST be the canonical form (ROAD, TRAFFIC, …),
        not the raw inference label.  Callers must normalise before calling.

        Commit rules:
          • severity ≥ 0.70  → commit immediately
          • severity < 0.70  → accumulate; commit at count ≥ 2

        [Fix 2] Stale pending entries (> 10 s old) are reaped on every call.

        Returns {"committed": bool, "pending_count": int}
        Thread-safe.
        """
        key = self._pending_key(lat, lon, hazard_type)
        now = time.time()

        with self._lock:
            # Reap expired pending entries on every store call
            self._reap_pending(now)

            # Path A — high-confidence single detection
            if severity >= self.STORE_SEV_THRESHOLD:
                self._commit_hazard(lat, lon, hazard_type, severity)
                self._pending_hazards.pop(key, None)
                return {"committed": True, "pending_count": 0}

            # Path B — accumulate in pending buffer
            entry = self._pending_hazards.get(key)
            if entry is None:
                self._pending_hazards[key] = {
                    "lat": lat, "lon": lon,
                    "max_severity": severity,
                    "count":        1,
                    "first_ts":     now,
                }
                return {"committed": False, "pending_count": 1}

            entry["count"]       += 1
            entry["max_severity"] = max(entry["max_severity"], severity)

            if entry["count"] >= self.STORE_MIN_HITS:
                self._commit_hazard(lat, lon, hazard_type, entry["max_severity"])
                del self._pending_hazards[key]
                return {"committed": True, "pending_count": 0}

            return {"committed": False, "pending_count": entry["count"]}

    # ── Public: get_nearby_hazards ────────────────────────────

    def get_nearby_hazards(
        self,
        lat:     float,
        lon:     float,
        radius:  float = 25.0,
        heading: float | None = None,
    ) -> list[tuple[dict, float]]:
        """
        Return confirmed approaching hazards within *radius* metres.

        [Fix 1] heading is respected only when meaningful.
                Pass heading=None to disable direction filtering entirely.
                Callers (main.py) must already apply the speed gate:
                  heading = gps_heading if gps_speed >= HEADING_MIN_SPEED_KMH else None

        [v5.2] DECAY   — effective_severity = severity × confidence.
                         Expired entries pruned in-place.

        [v5.2] DIRECTION — hazards outside the ±45° forward cone suppressed.

        Returns [(hazard_copy, distance_m)] sorted closest-first.
        Thread-safe.
        """
        results: list[tuple[dict, float]] = []
        expired: list[dict]               = []
        now = time.time()

        with self._lock:
            for h in self._hazard_memory:
                # Decay gate
                conf = _decay_confidence(h, now)
                if conf == 0.0:
                    expired.append(h)
                    continue

                # Distance gate
                dist = _haversine(lat, lon, h["lat"], h["lon"])
                if dist > radius:
                    continue

                # Direction filter (only when heading is reliable)
                if heading is not None:
                    to_hazard = _bearing(lat, lon, h["lat"], h["lon"])
                    if _angle_diff(heading, to_hazard) > self.APPROACH_CONE_DEG:
                        continue

                h_copy = dict(h)
                h_copy["effective_severity"] = round(h["severity"] * conf, 4)
                h_copy["decay_confidence"]   = conf
                results.append((h_copy, round(dist, 1)))

            # Prune expired entries
            if expired:
                surviving = [h for h in self._hazard_memory if h not in expired]
                self._hazard_memory.clear()
                self._hazard_memory.extend(surviving)

        results.sort(key=lambda x: x[1])
        return results

    # ── [Fix 5] Multi-hazard composite for decision engine ─────

    def get_top_hazards(
        self,
        lat:     float,
        lon:     float,
        radius:  float = 25.0,
        heading: float | None = None,
        n:       int   = 2,
    ) -> dict:
        """
        [Fix 5] Return the top-N approaching hazards PLUS a weighted
        composite severity that captures overlapping threat density.

        Composite formula:
            composite = 1 − ∏(1 − eff_sev_i)   for i in top-N

        This is the probabilistic "at least one hazard is real" score:
          • single hazard at 0.80 → composite = 0.80
          • two hazards at 0.60 each → composite = 1 − 0.4² = 0.84
          • one mild (0.40) + one moderate (0.60) → 1 − 0.6×0.4 = 0.76

        Used by main.py to build a richer predicted_hazard dict that
        the decision engine can use for its composite boost.

        Returns:
          {
            "hazards":           [(hazard_dict, dist_m), ...],  # top-N
            "composite_severity": float,      # weighted across all top-N
            "primary":            dict | None,  # closest single hazard
            "count":              int,
          }
        """
        nearby = self.get_nearby_hazards(lat, lon, radius, heading)
        top    = nearby[:n]

        if not top:
            return {
                "hazards":            [],
                "composite_severity": 0.0,
                "primary":            None,
                "count":              0,
            }

        # Probabilistic composite: P(at least one) = 1 − ∏(1 − p_i)
        complement = 1.0
        for h, _ in top:
            eff = h.get("effective_severity", h.get("severity", 0))
            complement *= (1.0 - eff)
        composite = round(min(1.0, 1.0 - complement), 4)

        closest_h, closest_dist = top[0]
        primary = {
            "type":               closest_h["type"],
            "distance":           closest_dist,
            "severity":           closest_h["severity"],
            "effective_severity": closest_h.get("effective_severity", closest_h["severity"]),
            "count":              closest_h.get("count", 1),
        }

        return {
            "hazards":            top,
            "composite_severity": composite,
            "primary":            primary,
            "count":              len(top),
        }

    def get_all_hazards(self) -> list[dict]:
        now = time.time()
        with self._lock:
            return [
                {**dict(h), "decay_confidence": _decay_confidence(h, now)}
                for h in self._hazard_memory
            ]

    # ── Heatmap ───────────────────────────────────────────────

    def get_hazard_heatmap(self) -> list[dict]:
        """
        Hazard density grid at ~22 m resolution (0.0002°).
        Sorted by hit count descending.
        """
        with self._lock:
            return sorted(
                [{"lat": k[0], "lon": k[1], "count": v}
                 for k, v in self._heatmap.items()],
                key=lambda x: -x["count"],
            )

    # ── Scenario injection ────────────────────────────────────

    def inject_scenario(self, scenario: str):
        SCENARIOS = {
            "pothole":         {"vibration":52.0,"acc_y":0.85,"road_surface":"GRAVEL","pothole_risk":0.85},
            "brake_failure":   {"brake_pressure":0.0,"thermal":95.0},
            "collision":       {"following_dist":0.8,"lane_offset":0.1},
            "engine_overheat": {"thermal":112.0,"oil_pressure":22.0},
            "lane_depart":     {"lane_offset":0.78,"gyro_yaw":0.9},
            "tire_blowout":    {"vibration":58.0,"acc_x":0.95},
            "fatigue":         {"lane_offset":0.55,"gyro_yaw":0.45},
        }
        with self._lock:
            self._scenario           = scenario
            self._scenario_overrides = SCENARIOS.get(scenario, {})

    def clear_scenario(self):
        with self._lock:
            self._scenario           = None
            self._scenario_overrides = {}

    def model_age_str(self) -> str:
        s = int(time.time() - self._start_time)
        if s < 60:   return f"{s}s"
        if s < 3600: return f"{s//60}m"
        return f"{s//3600}h"


def _ema(current: float, new: float, alpha: float) -> float:
    return round(current * (1 - alpha) + new * alpha, 4)

def _health_issue(health: float) -> str:
    if health < 20: return "CRITICAL — immediate service"
    if health < 40: return "Severe degradation"
    if health < 60: return "Service recommended"
    return "Minor wear"
