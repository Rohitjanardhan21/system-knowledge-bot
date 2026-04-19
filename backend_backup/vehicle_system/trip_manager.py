# backend/vehicle_system/trip_manager.py

import json
import os
import time

class TripManager:

    def __init__(self):
        self.current_trip = []
        self.trip_id = str(int(time.time()))

        self.base_path = "backend/vehicle_system/trip_storage"
        os.makedirs(self.base_path, exist_ok=True)

    def log(self, data):
        entry = {
            "timestamp": time.time(),
            "data": data
        }
        self.current_trip.append(entry)

    def save(self):
        if not self.current_trip:
            return None

        path = f"{self.base_path}/trip_{self.trip_id}.json"

        with open(path, "w") as f:
            json.dump(self.current_trip, f, indent=2)

        self.current_trip = []
        return path


trip_manager = TripManager()
