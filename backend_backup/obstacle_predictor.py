def predict_obstacle_risk(obstacle, speed):
    if not obstacle:
        return None

    # dummy distance (later replace with real estimation)
    distance = 6.0  

    time_to_impact = distance / max(speed, 0.1)

    if time_to_impact < 1:
        level = "CRITICAL"
        action = "BRAKE IMMEDIATELY"
    elif time_to_impact < 2.5:
        level = "HIGH"
        action = "SLOW DOWN"
    else:
        level = "LOW"
        action = "MONITOR"

    return {
        "distance": distance,
        "time_to_impact": time_to_impact,
        "hazard": {
            "level": level,
            "action": action
        }
    }
