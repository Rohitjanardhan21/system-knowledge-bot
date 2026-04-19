# backend/vehicle_context.py

def enrich_vehicle_context(features, vehicle_type="generic"):

    if vehicle_type == "2wheeler":
        return {
            **features,
            "thresholds": {
                "vibration": 0.6,
                "thermal": 85,
                "acoustic": 0.7
            },
            "vehicle_type": "2wheeler"
        }

    elif vehicle_type == "4wheeler":
        return {
            **features,
            "thresholds": {
                "vibration": 0.8,
                "thermal": 95,
                "acoustic": 0.85
            },
            "vehicle_type": "4wheeler"
        }

    return features
