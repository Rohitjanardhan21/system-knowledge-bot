"""
pipeline/hazard_utils.py  —  CVIS v5.3
────────────────────────────────────────
Stateless hazard utility functions used by main.py and decision.py.
No imports from other pipeline modules — zero circular-import risk.
"""

import math
import time


def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_between(from_lat, from_lon, to_lat, to_lon):
    """Compass bearing (°, 0=N, clockwise) from point 1 → 2."""
    phi1    = math.radians(from_lat)
    phi2    = math.radians(to_lat)
    dl      = math.radians(to_lon - from_lon)
    x = math.sin(dl) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def angle_diff(a, b):
    """Shortest angular separation → [0, 180]."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def is_approaching(veh_lat, veh_lon, veh_heading, haz_lat, haz_lon, cone_deg=45.0):
    """True if hazard is within the vehicle's forward cone."""
    return angle_diff(veh_heading, bearing_between(veh_lat, veh_lon, haz_lat, haz_lon)) <= cone_deg


# ── Hazard type inference ─────────────────────────────────────

def infer_hazard_type(vision=None, anomaly=None, sensors=None):
    """Priority: Vision → Sensors → Anomaly score. Returns raw type string."""
    if vision and vision.get("objects"):
        for obj in vision["objects"]:
            label = obj.get("label", "").lower()
            if any(w in label for w in ("pothole", "crack", "bump")):
                return "road_damage"
            if label in ("person", "pedestrian", "cyclist"):
                return "pedestrian"
            if label in ("car", "truck", "bus", "van", "motorcycle", "bike"):
                return "close_vehicle" if obj.get("distance", 100) < 10 else "traffic"
            if label in ("barrier", "cone", "debris", "obstacle"):
                return "obstacle"
    if sensors:
        if sensors.get("vibration", 0) > 0.7 or sensors.get("jerk", 0) > 0.6:
            return "road_damage"
        if sensors.get("brake_pressure", 0) > 70:
            return "traffic"
    if anomaly:
        s = anomaly.get("score", 0)
        if s > 0.80: return "critical_system_issue"
        if s > 0.60: return "vehicle_issue"
    return "unknown"


_CATEGORY_MAP = {
    "road_damage": "ROAD", "pothole": "ROAD", "crack": "ROAD", "bump": "ROAD",
    "traffic": "TRAFFIC", "close_vehicle": "TRAFFIC",
    "pedestrian": "HUMAN", "obstacle": "OBSTACLE",
    "vehicle_issue": "VEHICLE", "critical_system_issue": "VEHICLE",
    "unknown": "UNKNOWN",
}

def normalize_hazard_type(raw):
    return _CATEGORY_MAP.get(raw, "UNKNOWN")


def normalize_severity(score, min_val=0.0, max_val=1.0):
    if score is None: return 0.0
    return max(0.0, min(1.0, (score - min_val) / (max_val - min_val)))


def decay_hazard(hazard, current_time=None, decay_time=60*60*24*30):
    """Linear confidence ∈ [0,1]; 0 when expired."""
    if current_time is None: current_time = time.time()
    age = current_time - hazard.get("timestamp", current_time)
    if age >= decay_time: return 0.0
    return round(1.0 - age / decay_time, 4)


# ── Driver alert formatting ───────────────────────────────────

_ALERT_TEMPLATES = {
    "ROAD":     "Road damage ahead",
    "TRAFFIC":  "Traffic ahead",
    "HUMAN":    "Pedestrian ahead",
    "OBSTACLE": "Obstacle ahead",
    "VEHICLE":  "Vehicle issue detected",
    "UNKNOWN":  "Hazard ahead",
}

def format_driver_alert(hazard_type, distance):
    base = _ALERT_TEMPLATES.get(hazard_type, _ALERT_TEMPLATES["UNKNOWN"])
    dist_str = f" ({int(distance)}m)" if distance is not None else ""
    return base + dist_str


def _sev_label(eff_sev, dist):
    if eff_sev >= 0.75 or dist < 10:  return "CRITICAL"
    if eff_sev >= 0.50 or dist < 20:  return "WARNING"
    return "CAUTION"


def build_hazard_alerts(nearby, max_alerts=2):
    """
    Convert [(hazard_dict, dist_m)] → structured alert list.
    Sorted by effective_severity DESC, then distance ASC.
    Returns top max_alerts entries.
    """
    if not nearby:
        return []
    ranked = sorted(
        nearby,
        key=lambda x: (-x[0].get("effective_severity", x[0].get("severity", 0)), x[1]),
    )
    alerts = []
    for hazard, dist in ranked[:max_alerts]:
        canon   = normalize_hazard_type(hazard.get("type", "unknown"))
        sev     = hazard.get("severity", 0.5)
        eff_sev = hazard.get("effective_severity", sev)
        count   = hazard.get("count", 1)
        repeat  = f" [x{count} reports]" if count > 1 else ""
        alerts.append({
            "text":               format_driver_alert(canon, dist) + repeat,
            "sev":                _sev_label(eff_sev, dist),
            "type":               canon,
            "distance":           dist,
            "severity":           round(sev, 3),
            "effective_severity": round(eff_sev, 3),
            "decay_confidence":   round(hazard.get("decay_confidence", 1.0), 3),
            "count":              count,
        })
    return alerts


# ── UI model builder (feeds the driver HUD) ──────────────────

def build_ui_model(alerts, decision=None, confidence=1.0):
    """
    Collapse the backend alert list + decision into the minimal 4-field
    structure the driver HUD consumes:
        {action, reason, distance, severity}

    Priority:
      1. Nearest CRITICAL alert
      2. Nearest WARNING alert
      3. Decision engine action (SLOW_DOWN, STEER_CORRECT, etc.)
      4. SAFE fallback
    """
    ACTION_MAP = {
        "AUTO_BRAKE":    "Brake now",
        "SLOW_DOWN":     "Slow down",
        "REDUCE_SPEED":  "Slow down",
        "STEER_CORRECT": "Steer right",
        "ALERT_DRIVER":  "Check surroundings",
        "INCREASE_DIST": "Increase distance",
        "LANE_KEEP":     "Stay in lane",
        "MAINTAIN":      "Safe",
    }

    if confidence < 0.4:
        return {"action": "Check surroundings", "reason": "Uncertain conditions",
                "distance": None, "severity": "CAUTION"}

    if alerts:
        top = alerts[0]
        dist = top.get("distance")
        sev  = top.get("sev", "WARNING")
        rtype = top.get("type", "UNKNOWN")
        reason = _ALERT_TEMPLATES.get(rtype, "Hazard ahead")

        if dist is not None and dist < 10:
            action = "Brake now"
        elif dist is not None and dist < 25:
            action = "Slow down"
        else:
            action = "Slow down" if sev != "SAFE" else "Safe"

        return {"action": action, "reason": reason, "distance": dist, "severity": sev}

    if decision:
        eng_action = decision.get("action", "MAINTAIN")
        label      = ACTION_MAP.get(eng_action, "Check surroundings")
        if eng_action == "MAINTAIN":
            return {"action": "Safe", "reason": "No hazards ahead",
                    "distance": None, "severity": "SAFE"}
        return {"action": label, "reason": "Caution advised",
                "distance": None, "severity": "CAUTION"}

    return {"action": "Safe", "reason": "No hazards ahead",
            "distance": None, "severity": "SAFE"}
