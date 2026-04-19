# backend/vehicle_system/component_health_model.py

class ComponentHealthModel:

    def analyze(self, signals):
        issues = []

        temp = signals.get("temperature", 0)
        vibration = signals.get("vibration", 0)

        if temp > 90 and vibration > 7:
            issues.append({
                "component": "engine",
                "issue": "possible_internal_stress",
                "severity": "HIGH"
            })

        if vibration > 8:
            issues.append({
                "component": "suspension",
                "issue": "possible_wear_or_road_damage",
                "severity": "MEDIUM"
            })

        return issues


component_health_model = ComponentHealthModel()
