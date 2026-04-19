# backend/vehicle_system/driver_behavior_model.py

class DriverBehaviorModel:

    def __init__(self):
        self.profile = {
            "aggressive": False,
            "smooth": True
        }

    def update(self, signals):
        accel = signals.get("acceleration", 0)
        brake = signals.get("braking", 0)

        if accel > 8 or brake > 8:
            self.profile["aggressive"] = True
            self.profile["smooth"] = False

        return self.profile


driver_behavior_model = DriverBehaviorModel()
