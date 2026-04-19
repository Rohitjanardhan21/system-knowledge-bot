"""
pipeline/sensors.py  —  CVIS v5.0  (final)
────────────────────────────────────────────
Layer 3 — Real Hardware Sensor Integration

Threads:
  • OBD-II loop    (10 Hz)   — ELM327 via python-obd
  • IMU loop       (50 Hz)   — MPU-6050 via smbus2 (I²C)
  • GPS loop        (1 Hz)   — gpsd via gpsd-py3
  • Synthetic loop (10 Hz)   — physics-model fallback
  • Fusion loop    (20 Hz)   — Kalman filter + timestamp gating (Fix 3)

Fix 3 — Timestamp Synchronisation:
  Every sensor write stamps time.time() into _raw_ts[source].
  The Kalman fusion loop gates each signal before fusing:

      age = now - _raw_ts[source]
      if age < STALE_THRESHOLDS[source]:
          fused[k] = kalman.update(raw_value)   # fresh → update
      else:
          fused[k] = kalman.get()               # stale → hold last estimate

  A "sensor_staleness" dict is forwarded to SystemState and
  exposed in the API response so the frontend can show which
  streams are lagging.

Graceful degradation:
  OBD offline  → speed/RPM/temps from physics model
  IMU offline  → acc/gyro from physics model
  GPS offline  → speed from OBD
  All offline  → full synthetic physics model

Install extras:
  pip install obd smbus2 gpsd-py3
"""

import asyncio
import logging
import math
import random
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.pipeline.state import SystemState

log = logging.getLogger("cvis.sensors")

# ── Staleness thresholds (seconds) per source ─────────────────
STALE_THRESHOLDS: dict[str, float] = {
    "imu":       0.10,   # IMU at 50 Hz — stale after 100 ms
    "obd":       0.50,   # OBD at 10 Hz — stale after 500 ms
    "gps":       2.00,   # GPS at  1 Hz — stale after 2 s
    "synthetic": 0.20,   # Fallback at 10 Hz — stale after 200 ms
}

try:
    import obd
    _OBD_OK = True
except ImportError:
    _OBD_OK = False

try:
    import smbus2
    _IMU_OK = True
except ImportError:
    _IMU_OK = False

try:
    import gpsd
    _GPS_OK = True
except ImportError:
    _GPS_OK = False


# ═══════════════════════════════════════════════════════════════
#  KALMAN 1-D FILTER
# ═══════════════════════════════════════════════════════════════
class Kalman1D:
    def __init__(self, Q: float = 0.01, R: float = 0.5):
        self.Q = Q; self.R = R
        self.P = 1.0; self.x = 0.0; self.init = False

    def update(self, z: float) -> float:
        if not self.init:
            self.x = z; self.init = True; return z
        self.P += self.Q
        K       = self.P / (self.P + self.R)
        self.x += K * (z - self.x)
        self.P *= 1 - K
        return self.x

    def get(self) -> float:
        """Return current state estimate without updating (for stale signals)."""
        return self.x


KALMAN_PARAMS: dict[str, tuple[float, float]] = {
    "speed":          (0.5,  2.0),
    "rpm":            (5.0, 20.0),
    "thermal":        (0.1,  1.0),
    "oil_pressure":   (0.3,  2.0),
    "fuel_level":     (0.01, 0.1),
    "battery_voltage":(0.05, 0.2),
    "brake_pressure": (0.3,  2.0),
    "acc_x":          (0.05, 0.5),
    "acc_y":          (0.05, 0.5),
    "acc_z":          (0.05, 0.3),
    "gyro_yaw":       (0.1,  0.5),
    "gps_speed":      (0.3,  2.0),
    "lane_offset":    (0.05, 0.3),
    "vibration":      (0.2,  3.0),
}


class SensorHub:
    """Manages all hardware sensor threads and Kalman-fused snapshots."""

    OBD_PIDS = {
        "speed":           obd.commands.SPEED                    if _OBD_OK else None,
        "rpm":             obd.commands.RPM                      if _OBD_OK else None,
        "thermal":         obd.commands.COOLANT_TEMP             if _OBD_OK else None,
        "oil_pressure":    obd.commands.OIL_TEMP                 if _OBD_OK else None,
        "throttle":        obd.commands.THROTTLE_POS             if _OBD_OK else None,
        "fuel_level":      obd.commands.FUEL_LEVEL               if _OBD_OK else None,
        "battery_voltage": obd.commands.CONTROL_MODULE_VOLTAGE   if _OBD_OK else None,
    }

    MPU_ADDR   = 0x68
    MPU_REGS   = {"pwr":0x6B,"acc_x":0x3B,"acc_y":0x3D,"acc_z":0x3F,
                  "gyro_x":0x43,"gyro_y":0x45,"gyro_z":0x47}
    ACC_SCALE  = 16384.0
    GYRO_SCALE = 131.0

    # Signal → source mapping for staleness gating
    _SIGNAL_SOURCE: dict[str, str] = {
        "acc_x":"imu","acc_y":"imu","acc_z":"imu",
        "gyro_yaw":"imu","brake_pressure":"imu","vibration":"imu",
        "speed":"obd","rpm":"obd","thermal":"obd",
        "oil_pressure":"obd","fuel_level":"obd","battery_voltage":"obd",
        "gps_speed":"gps","gps_lat":"gps","gps_lon":"gps","gps_alt":"gps",
    }

    def __init__(self, state: "SystemState"):
        self.state    = state
        self._running = False
        self._tasks: list[asyncio.Task] = []

        self._kf: dict[str, Kalman1D] = {
            k: Kalman1D(*v) for k, v in KALMAN_PARAMS.items()
        }

        self._obd_conn = None
        self._imu_bus  = None

        self.obd_connected = False
        self.imu_connected = False
        self.gps_connected = False

        self._raw:  dict = {}
        # Fix 3: per-source write timestamps
        self._raw_ts: dict[str, float] = {
            "imu": 0.0, "obd": 0.0, "gps": 0.0, "synthetic": 0.0
        }
        self._lock = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────

    async def start(self):
        self._running = True
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self._init_obd)
        loop.run_in_executor(None, self._init_imu)
        loop.run_in_executor(None, self._init_gps)
        self._tasks = [
            asyncio.create_task(self._obd_loop()),
            asyncio.create_task(self._imu_loop()),
            asyncio.create_task(self._gps_loop()),
            asyncio.create_task(self._synthetic_loop()),
            asyncio.create_task(self._fusion_loop()),
        ]
        log.info("SensorHub started")

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        if self._obd_conn: self._obd_conn.close()
        if self._imu_bus:  self._imu_bus.close()

    # ── OBD-II ───────────────────────────────────────────────

    def _init_obd(self):
        if not _OBD_OK:
            log.info("python-obd not installed — OBD simulation mode")
            return
        try:
            self._obd_conn = obd.OBD(portstr=None, baudrate=38400,
                                     protocol=None, fast=True, timeout=5)
            if self._obd_conn.is_connected():
                self.obd_connected = True
                log.info(f"OBD-II connected: {self._obd_conn.port_name()}")
        except Exception as e:
            log.warning(f"OBD-II init failed ({e})")

    async def _obd_loop(self):
        while self._running:
            if self.obd_connected and self._obd_conn:
                await asyncio.get_event_loop().run_in_executor(None, self._poll_obd)
            await asyncio.sleep(0.1)

    def _poll_obd(self):
        try:
            updates = {}
            for key, cmd in self.OBD_PIDS.items():
                if cmd is None: continue
                resp = self._obd_conn.query(cmd)
                if resp.is_null(): continue
                val = float(resp.value.magnitude)
                if key == "speed":    val *= 0.621371
                if key == "fuel_level": val /= 100.0
                updates[key] = val
            with self._lock:
                self._raw.update(updates)
                self._raw_ts["obd"] = time.time()   # Fix 3: stamp OBD write
        except Exception as e:
            log.debug(f"OBD poll error: {e}")

    # ── IMU (MPU-6050) ────────────────────────────────────────

    def _init_imu(self):
        if not _IMU_OK:
            log.info("smbus2 not installed — IMU simulation mode")
            return
        try:
            self._imu_bus = smbus2.SMBus(1)
            self._imu_bus.write_byte_data(self.MPU_ADDR, self.MPU_REGS["pwr"], 0)
            self.imu_connected = True
            log.info("MPU-6050 IMU connected on I²C bus 1")
        except Exception as e:
            log.warning(f"IMU init failed ({e})")

    async def _imu_loop(self):
        while self._running:
            if self.imu_connected and self._imu_bus:
                await asyncio.get_event_loop().run_in_executor(None, self._poll_imu)
            await asyncio.sleep(0.02)

    def _poll_imu(self):
        def read_word(reg):
            hi = self._imu_bus.read_byte_data(self.MPU_ADDR, reg)
            lo = self._imu_bus.read_byte_data(self.MPU_ADDR, reg+1)
            v  = (hi << 8) + lo
            return v - 65536 if v >= 32768 else v
        try:
            ax = read_word(self.MPU_REGS["acc_x"])  / self.ACC_SCALE
            ay = read_word(self.MPU_REGS["acc_y"])  / self.ACC_SCALE
            az = read_word(self.MPU_REGS["acc_z"])  / self.ACC_SCALE
            gz = read_word(self.MPU_REGS["gyro_z"]) / self.GYRO_SCALE
            with self._lock:
                self._raw.update({
                    "acc_x": ax, "acc_y": ay, "acc_z": az,
                    "gyro_yaw": gz,
                    "brake_pressure": max(0.0, -ay * 30),
                })
                self._raw_ts["imu"] = time.time()   # Fix 3: stamp IMU write
        except Exception as e:
            log.debug(f"IMU error: {e}")

    # ── GPS ───────────────────────────────────────────────────

    def _init_gps(self):
        if not _GPS_OK:
            log.info("gpsd-py3 not installed — GPS simulation mode")
            return
        try:
            gpsd.connect()
            self.gps_connected = True
            log.info("GPS connected via gpsd")
        except Exception as e:
            log.warning(f"GPS init failed ({e})")

    async def _gps_loop(self):
        while self._running:
            if self.gps_connected:
                await asyncio.get_event_loop().run_in_executor(None, self._poll_gps)
            await asyncio.sleep(1.0)

    def _poll_gps(self):
        try:
            pkt = gpsd.get_current()
            with self._lock:
                self._raw["gps_speed"] = float(pkt.hspeed() or 0) * 2.237
                self._raw["gps_lat"]   = pkt.lat
                self._raw["gps_lon"]   = pkt.lon
                self._raw["gps_alt"]   = pkt.alt
                self._raw_ts["gps"]    = time.time()   # Fix 3: stamp GPS write
        except Exception as e:
            log.debug(f"GPS error: {e}")

    # ── Synthetic physics model ───────────────────────────────

    async def _synthetic_loop(self):
        t     = 0.0
        speed = 55.0
        rpm   = 2200.0
        temp  = 88.0
        brake = 0.0
        while self._running:
            t += 0.1
            target_speed = 55 + 25 * math.sin(t * 0.06)
            speed  = speed + (target_speed - speed) * 0.05 + random.gauss(0, 0.4)
            rpm    = 800 + speed * 30 + random.gauss(0, 80)
            temp   = 75 + speed * 0.22 + random.gauss(0, 0.5)
            brake  = max(0, (55-speed)*0.8 + random.gauss(0, 2))
            acc_y  = -(speed-target_speed)*0.03 + random.gauss(0, 0.05)
            acc_x  = math.sin(t*0.3)*0.15 + random.gauss(0, 0.03)
            acc_z  = 0.98 + random.gauss(0, 0.01)
            gyro   = math.sin(t*0.4)*0.25 + random.gauss(0, 0.05)
            lane   = math.sin(t*0.07)*0.25 + random.gauss(0, 0.02)
            vib    = 3 + speed*0.12 + abs(acc_y)*8 + random.gauss(0, 1)

            with self._lock:
                if not self.obd_connected:
                    self._raw["speed"]           = round(max(0, speed), 2)
                    self._raw["rpm"]             = round(max(0, rpm), 1)
                    self._raw["thermal"]         = round(temp, 2)
                    self._raw["oil_pressure"]    = round(45 + speed*0.35, 1)
                    self._raw["fuel_level"]      = 0.72
                    self._raw["battery_voltage"] = round(13.6 + random.gauss(0,0.05), 2)
                if not self.imu_connected:
                    self._raw["acc_x"]          = round(acc_x, 4)
                    self._raw["acc_y"]          = round(acc_y, 4)
                    self._raw["acc_z"]          = round(acc_z, 4)
                    self._raw["gyro_yaw"]       = round(gyro, 4)
                    self._raw["brake_pressure"] = round(max(0, brake), 2)
                    self._raw["vibration"]      = round(max(0, vib), 2)
                if not self.gps_connected:
                    self._raw["gps_speed"] = round(speed, 2)
                    self._raw["gps_lat"]   = 37.7749 + t*0.000002
                    self._raw["gps_lon"]   = -122.4194 + t*0.000001

                self._raw["lane_offset"]    = round(lane, 4)
                self._raw["road_surface"]   = "WET" if abs(acc_x) > 0.3 else "DRY"
                self._raw["friction"]       = round(0.85 - abs(acc_x)*0.2, 3)
                self._raw["following_dist"] = round(2.5 + abs(math.sin(t*0.1))*2.5, 2)
                self._raw["speed_limit"]    = 70
                self._raw["curvature"]      = round(abs(math.sin(t*0.15))*0.2, 3)
                self._raw["pothole_risk"]   = round(abs(math.sin(t*2.5))*0.15, 3)
                self._raw_ts["synthetic"]   = time.time()   # Fix 3: stamp synthetic write

            await asyncio.sleep(0.1)

    # ── Kalman fusion loop — Fix 3: staleness gating ─────────

    async def _fusion_loop(self):
        """
        Apply Kalman filters with per-source staleness gating.

        For each signal:
          • If its source wrote recently (age < threshold) → update Kalman
          • If stale → hold last Kalman estimate without updating
        Writes staleness report to SystemState for API exposure.
        """
        while self._running:
            now = time.time()
            with self._lock:
                raw_copy = dict(self._raw)
                ts_copy  = dict(self._raw_ts)

            # Build staleness report
            staleness: dict[str, str] = {}
            for source, threshold in STALE_THRESHOLDS.items():
                age = now - ts_copy.get(source, 0.0)
                staleness[source] = (
                    f"OK ({age*1000:.0f}ms)"
                    if age < threshold
                    else f"STALE ({age*1000:.0f}ms > {threshold*1000:.0f}ms)"
                )

            fused: dict = {}
            for k, v in raw_copy.items():
                if not isinstance(v, (float, int)):
                    fused[k] = v
                    continue
                source = self._SIGNAL_SOURCE.get(k, "synthetic")
                age    = now - ts_copy.get(source, 0.0)
                thresh = STALE_THRESHOLDS.get(source, 1.0)

                if age > thresh:
                    # Stale: return last Kalman estimate, do NOT update
                    fused[k] = round(self._kf[k].get() if k in self._kf else float(v), 4)
                else:
                    # Fresh: update Kalman
                    fused[k] = round(self._kf[k].update(float(v)) if k in self._kf else float(v), 4)

            fused["_staleness"] = staleness
            fused["_fusion_ts"] = now
            self.state.update_sensors(fused)
            await asyncio.sleep(0.05)   # 20 Hz
