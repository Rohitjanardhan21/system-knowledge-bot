# ---------------------------------------------------------
# 🚗 VEHICLE CONTEXT ENGINE (PRODUCTION VERSION)
# ---------------------------------------------------------

from datetime import datetime


# ---------------------------------------------------------
# 🧠 SPEED CONTEXT
# ---------------------------------------------------------
def classify_speed(speed):
    if speed < 10:
        return "idle"
    elif speed < 30:
        return "slow"
    elif speed < 60:
        return "moderate"
    elif speed < 90:
        return "fast"
    return "high_speed"


# ---------------------------------------------------------
# 🧠 ROAD CONTEXT (BASIC HEURISTIC)
# ---------------------------------------------------------
def estimate_road_type(vibration, speed):
    if vibration > 0.7:
        return "rough"
    if speed > 60 and vibration < 0.3:
        return "highway"
    if speed < 40:
        return "urban"
    return "mixed"


# ---------------------------------------------------------
# 🧠 RIDER / VEHICLE TYPE CONTEXT
# ---------------------------------------------------------
def classify_vehicle(vehicle_type):
    if vehicle_type in ["bike", "2wheeler"]:
        return "two_wheeler"
    elif vehicle_type in ["car", "4wheeler"]:
        return "four_wheeler"
    return "unknown"


# ---------------------------------------------------------
# 🧠 RISK EVALUATION
# ---------------------------------------------------------
def compute_risk(speed, vibration, anomaly_score):
    risk = 0

    # Speed contribution
    if speed > 70:
        risk += 2
    elif speed > 40:
        risk += 1

    # Vibration contribution
    if vibration > 0.8:
        risk += 2
    elif vibration > 0.5:
        risk += 1

    # AI anomaly contribution
    if anomaly_score > 2:
        risk += 3
    elif anomaly_score > 1:
        risk += 1

    if risk >= 5:
        return "critical"
    elif risk >= 3:
        return "high"
    elif risk >= 1:
        return "medium"
    return "low"


# ---------------------------------------------------------
# 🧠 MAIN CONTEXT ENGINE
# ---------------------------------------------------------
def enrich_vehicle_context(data):

    speed = float(data.get("speed", 0))
    vibration = max(data.get("vibration", [0])) if isinstance(data.get("vibration"), list) else data.get("vibration", 0)
    anomaly_score = float(data.get("anomaly_score", 0))
    vehicle_type = data.get("vehicle_type", "2wheeler")

    context = {
        "timestamp": datetime.utcnow().isoformat(),

        # 🚗 VEHICLE INFO
        "vehicle_type": classify_vehicle(vehicle_type),

        # 🚦 MOTION
        "speed": speed,
        "speed_class": classify_speed(speed),

        # 🛣 ROAD
        "road_type": estimate_road_type(vibration, speed),

        # ⚠ RISK
        "risk_level": compute_risk(speed, vibration, anomaly_score),

        # 📊 RAW SNAPSHOT
        "raw": {
            "vibration": vibration,
            "anomaly_score": anomaly_score
        }
    }

    return context
