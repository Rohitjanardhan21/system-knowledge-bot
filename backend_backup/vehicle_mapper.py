# backend/vehicle_mapper.py

def map_to_vehicle_domain(system_output):

    anomaly = system_output.get("anomaly_score", 0)

    if anomaly > 1.5:
        return "critical_vehicle_issue"

    if anomaly > 0.8:
        return "moderate_vehicle_issue"

    return "normal_operation"
