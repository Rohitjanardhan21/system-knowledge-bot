# ---------------------------------------------------------
# 🧠 SENSOR INGESTION ENGINE (REAL + FALLBACK SAFE)
# ---------------------------------------------------------

import time
import threading
import random
from collections import deque

import psutil
import numpy as np

# Optional (install if using real mic)
try:
    import sounddevice as sd
    AUDIO_ENABLED = True
except:
    AUDIO_ENABLED = False


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

WINDOW_SIZE = 50
AUDIO_SAMPLE_RATE = 16000
AUDIO_DURATION = 0.5  # seconds

# ---------------------------------------------------------
# SENSOR ENGINE
# ---------------------------------------------------------

class SensorIngestion:

    def __init__(self):
        self.running = False

        self.data = {
            "cpu": 0,
            "memory": 0,
            "temp": 0,
            "audio": [],
            "vibration": [],
            "current": 0,
            "timestamp": time.time()
        }

        self.lock = threading.Lock()

        # history buffers
        self.audio_buffer = deque(maxlen=WINDOW_SIZE)
        self.vibration_buffer = deque(maxlen=WINDOW_SIZE)

    # -----------------------------------------------------
    # CPU + MEMORY (REAL)
    # -----------------------------------------------------
    def read_system_metrics(self):
        return {
            "cpu": psutil.cpu_percent(interval=0.2),
            "memory": psutil.virtual_memory().percent
        }

    # -----------------------------------------------------
    # TEMPERATURE (REAL IF AVAILABLE)
    # -----------------------------------------------------
    def read_temperature(self):
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name in temps:
                    if temps[name]:
                        return temps[name][0].current
        except:
            pass

        # fallback simulation
        return random.uniform(40, 75)

    # -----------------------------------------------------
    # AUDIO (REAL MIC)
    # -----------------------------------------------------
    def read_audio(self):

        if not AUDIO_ENABLED:
            # fallback: simulated noise
            return np.random.normal(0, 0.1, 200).tolist()

        try:
            recording = sd.rec(
                int(AUDIO_SAMPLE_RATE * AUDIO_DURATION),
                samplerate=AUDIO_SAMPLE_RATE,
                channels=1,
                dtype="float32"
            )
            sd.wait()

            return recording.flatten().tolist()

        except Exception:
            return []

    # -----------------------------------------------------
    # VIBRATION (SIMULATED / SENSOR READY)
    # -----------------------------------------------------
    def read_vibration(self):

        # Replace with real IMU sensor later (MPU6050 etc.)
        return np.random.uniform(0, 1, 20).tolist()

    # -----------------------------------------------------
    # ELECTRICAL (SIMULATED)
    # -----------------------------------------------------
    def read_current(self):
        return random.uniform(10, 90)

    # -----------------------------------------------------
    # COLLECT ALL
    # -----------------------------------------------------
    def collect(self):

        sys = self.read_system_metrics()
        temp = self.read_temperature()
        audio = self.read_audio()
        vibration = self.read_vibration()
        current = self.read_current()

        with self.lock:
            self.data = {
                "cpu": sys["cpu"],
                "memory": sys["memory"],
                "temp": temp,
                "audio": audio,
                "vibration": vibration,
                "current": current,
                "timestamp": time.time()
            }

    # -----------------------------------------------------
    # BACKGROUND LOOP
    # -----------------------------------------------------
    def start(self, interval=1.0):

        if self.running:
            return

        self.running = True

        def loop():
            while self.running:
                try:
                    self.collect()
                except Exception as e:
                    print("Sensor error:", e)

                time.sleep(interval)

        threading.Thread(target=loop, daemon=True).start()

    # -----------------------------------------------------
    # STOP
    # -----------------------------------------------------
    def stop(self):
        self.running = False

    # -----------------------------------------------------
    # GET LATEST DATA
    # -----------------------------------------------------
    def get_data(self):
        with self.lock:
            return self.data.copy()


# ---------------------------------------------------------
# GLOBAL INSTANCE (EASY IMPORT)
# ---------------------------------------------------------

sensor_engine = SensorIngestion()
