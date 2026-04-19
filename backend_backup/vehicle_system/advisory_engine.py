# backend/vehicle_system/advisory_engine.py

class AdvisoryEngine:

    def generate(self, predictions, issues, driver_profile):
        advisories = []

        for p in predictions:
            if p["type"] == "engine_overheating":
                advisories.append("⚠ Engine temperature rising. Consider slowing down.")

        for i in issues:
            if i["component"] == "suspension":
                advisories.append("⚠ Rough road detected. Reduce speed.")

        if driver_profile["aggressive"]:
            advisories.append("⚠ Aggressive driving detected. Ride smoother.")

        return advisories


advisory_engine = AdvisoryEngine()
