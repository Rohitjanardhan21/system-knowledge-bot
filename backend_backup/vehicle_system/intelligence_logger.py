# ---------------------------------------------------------
# 🧠 INTELLIGENCE LOGGER (LEVEL 8 - FAST + DATASET READY)
# ---------------------------------------------------------

import json
import time
from pathlib import Path
from collections import deque


class IntelligenceLogger:

    def __init__(self):
        # Base paths
        self.base_path = Path("backend/vehicle_system/logs")

        self.frames_path = self.base_path / "frames"
        self.trips_path = self.base_path / "trips"
        self.meta_path = self.base_path / "meta"

        # Create directories
        self.frames_path.mkdir(parents=True, exist_ok=True)
        self.trips_path.mkdir(parents=True, exist_ok=True)
        self.meta_path.mkdir(parents=True, exist_ok=True)

        # Runtime buffers
        self.current_trip = []
        self.trip_id = str(int(time.time()))

        # 🔥 NEW: in-memory fast cache (for dashboard)
        self.latest_frame_cache = None
        self.frame_buffer = deque(maxlen=200)  # replay buffer

    # -----------------------------------------------------
    # 🔹 LOG SINGLE FRAME (REAL-TIME)
    # -----------------------------------------------------
    def log_frame(self, data):
        try:
            timestamp = int(time.time() * 1000)

            payload = {
                "timestamp": timestamp,
                "data": data
            }

            # 🔥 CACHE (fast access for dashboard)
            self.latest_frame_cache = payload
            self.frame_buffer.append(payload)

            # 🔥 DISK WRITE (async-safe simple write)
            filename = self.frames_path / f"frame_{timestamp}.json"

            with open(filename, "w") as f:
                json.dump(payload, f)

            # 🔥 TRIP BUFFER
            self.current_trip.append(payload)

        except Exception as e:
            print(f"[Logger] Frame logging error: {e}")

    # -----------------------------------------------------
    # 🔹 SAVE COMPLETE TRIP
    # -----------------------------------------------------
    def save_trip(self):
        try:
            if not self.current_trip:
                return None

            path = self.trips_path / f"trip_{self.trip_id}.json"

            with open(path, "w") as f:
                json.dump(self.current_trip, f)

            # Reset
            self.current_trip = []
            self.trip_id = str(int(time.time()))

            return str(path)

        except Exception as e:
            print(f"[Logger] Trip save error: {e}")
            return None

    # -----------------------------------------------------
    # 🔹 EXPORT DATASET (FOR ML TRAINING)
    # -----------------------------------------------------
    def export_dataset(self, path="dataset.json"):
        try:
            dataset = []

            for frame in self.frame_buffer:
                data = frame.get("data", {})
                features = data.get("perception", {}).get("features", {})

                if features:
                    dataset.append(features)

            with open(path, "w") as f:
                json.dump(dataset, f)

            return path

        except Exception as e:
            print(f"[Logger] Dataset export error: {e}")
            return None

    # -----------------------------------------------------
    # 🔹 LOG META EVENTS
    # -----------------------------------------------------
    def log_event(self, message, level="INFO"):
        try:
            timestamp = int(time.time() * 1000)

            filename = self.meta_path / "events.log"

            entry = {
                "timestamp": timestamp,
                "level": level,
                "message": message
            }

            with open(filename, "a") as f:
                f.write(json.dumps(entry) + "\n")

        except Exception as e:
            print(f"[Logger] Event logging error: {e}")

    # -----------------------------------------------------
    # 🔹 GET LATEST FRAME (FAST - CACHE FIRST)
    # -----------------------------------------------------
    def get_latest_frame(self):
        try:
            if self.latest_frame_cache:
                return self.latest_frame_cache

            # fallback to disk
            files = sorted(self.frames_path.glob("*.json"), reverse=True)
            if not files:
                return None

            with open(files[0]) as f:
                return json.load(f)

        except Exception as e:
            print(f"[Logger] Read error: {e}")
            return None

    # -----------------------------------------------------
    # 🔹 GET FRAME BY INDEX (REPLAY)
    # -----------------------------------------------------
    def get_frame_by_index(self, index):
        try:
            if index < 0 or index >= len(self.frame_buffer):
                return None

            return list(self.frame_buffer)[index]

        except Exception as e:
            print(f"[Logger] Replay error: {e}")
            return None

    # -----------------------------------------------------
    # 🔹 GET RECENT FRAMES (TIMELINE)
    # -----------------------------------------------------
    def get_recent_frames(self, limit=50):
        try:
            return list(self.frame_buffer)[-limit:]
        except:
            return []

    # -----------------------------------------------------
    # 🔹 LIST ALL TRIPS
    # -----------------------------------------------------
    def list_trips(self):
        try:
            return sorted([str(p) for p in self.trips_path.glob("*.json")])
        except:
            return []

    # -----------------------------------------------------
    # 🔹 LOAD TRIP
    # -----------------------------------------------------
    def load_trip(self, path):
        try:
            with open(path) as f:
                return json.load(f)
        except:
            return None


# ---------------------------------------------------------
# 🔥 GLOBAL INSTANCE
# ---------------------------------------------------------
intelligence_logger = IntelligenceLogger()
