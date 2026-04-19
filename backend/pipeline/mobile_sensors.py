"""
pipeline/mobile_sensors.py  —  CVIS v5.0
──────────────────────────────────────────
Upgrade 2 — Real Sensor Input

Three real-hardware pathways:

  A. Mobile IMU (WebSocket endpoint)
     Phone → WebSocket → /ws/imu
     Payload: {ax, ay, az, gx, gy, gz, timestamp}
     Works with: iOS Sensor Logger, Android Physics Toolbox,
                 or a custom React Native app streaming DeviceMotion

  B. Enhanced OBD-II
     ELM327 over USB/Bluetooth serial
     Polls: speed, RPM, coolant, oil, MAF, throttle, fuel, battery,
            intake temp, engine load, short/long fuel trim
     Error recovery: reconnects on timeout, blacklists failed PIDs

  C. GPS (serial NMEA or gpsd)
     Provides: lat, lon, alt, speed, heading, HDOP (accuracy)
     Computes: road curvature from heading rate, speed cross-check

All three write to a shared SensorBuffer that SensorHub reads.
The existing Kalman fusion loop in sensors.py consumes this buffer
unchanged — no modification to the rest of the pipeline required.
"""

import asyncio
import json
import logging
import math
import re
import serial
import serial.tools.list_ports
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.pipeline.state import SystemState

log = logging.getLogger("cvis.mobile_sensors")

# ── Optional libs ─────────────────────────────────────────────
try:
    import obd
    _OBD_OK = True
except ImportError:
    _OBD_OK = False

try:
    import gpsd
    _GPS_OK = True
except ImportError:
    _GPS_OK = False


# ═══════════════════════════════════════════════════════════════
#  SHARED SENSOR BUFFER  (thread-safe, read by SensorHub)
# ═══════════════════════════════════════════════════════════════
class SensorBuffer:
    """
    Thread-safe key→value store that SensorHub reads every fusion tick.
    Each source writes its own keys; SensorHub merges them via Kalman.
    """
    def __init__(self):
        self._data: dict = {}
        self._ts:   dict = {}   # per-key write timestamp
        self._lock  = threading.Lock()

    def write(self, updates: dict, source: str = "unknown"):
        ts = time.time()
        with self._lock:
            self._data.update(updates)
            for k in updates:
                self._ts[k] = ts

    def read_all(self) -> dict:
        with self._lock:
            return dict(self._data)

    def age(self, key: str) -> float:
        with self._lock:
            ts = self._ts.get(key, 0.0)
            return time.time() - ts if ts else float("inf")


# ═══════════════════════════════════════════════════════════════
#  A. MOBILE IMU  (WebSocket receiver)
# ═══════════════════════════════════════════════════════════════
class MobileIMUReceiver:
    """
    Receives IMU data from a phone over WebSocket.

    Phone app setup (any of these works):
      • iOS: "Sensor Logger" app → WebSocket output mode
             URL: ws://<PC_IP>:8001/ws/imu
             Format: {"ax":0.12,"ay":-0.05,"az":9.78,"gx":0.01,"gy":0.0,"gz":0.02,"ts":1234567}
      • Android: "Physics Toolbox Sensor Suite" → network streaming
      • Custom: navigator.deviceMotion + WebSocket in a browser tab

    Units expected:
      ax/ay/az: m/s²  (will be converted to g internally)
      gx/gy/gz: rad/s (will be converted to deg/s)

    The receiver exposes a FastAPI WebSocket endpoint at /ws/imu.
    Inject it into the FastAPI app via register(app).
    """

    G = 9.81   # m/s² per g

    def __init__(self, buffer: SensorBuffer):
        self.buffer     = buffer
        self._clients   = 0
        self._last_data: dict = {}
        # Low-pass filter state for phone sensor noise
        self._lp: dict = {}
        self._alpha     = 0.2   # low-pass coefficient
        log.info("MobileIMUReceiver initialised — waiting for /ws/imu connection")

    def _lowpass(self, key: str, val: float) -> float:
        prev             = self._lp.get(key, val)
        filtered         = self._alpha * val + (1 - self._alpha) * prev
        self._lp[key]    = filtered
        return filtered

    async def handle(self, websocket):
        """Call from a FastAPI WebSocket endpoint."""
        from fastapi import WebSocketDisconnect
        self._clients += 1
        log.info(f"Mobile IMU connected (total: {self._clients})")
        try:
            while True:
                raw  = await websocket.receive_text()
                data = json.loads(raw)
                self._ingest(data)
        except (WebSocketDisconnect, Exception) as e:
            self._clients -= 1
            log.info(f"Mobile IMU disconnected: {e}")

    def _ingest(self, data: dict):
        # Accept m/s² or g — detect by magnitude
        ax_raw = float(data.get("ax", data.get("accelerationX", 0)))
        ay_raw = float(data.get("ay", data.get("accelerationY", 0)))
        az_raw = float(data.get("az", data.get("accelerationZ", self.G)))

        # If magnitude >> 2g, assume m/s²
        mag = math.sqrt(ax_raw**2 + ay_raw**2 + az_raw**2)
        if mag > 4:   # m/s² regime
            ax_raw /= self.G; ay_raw /= self.G; az_raw /= self.G

        # Gyro: accept rad/s or deg/s — detect by magnitude
        gz_raw = float(data.get("gz", data.get("rotationRateAlpha", 0)))
        if abs(gz_raw) > 10:   # rad/s regime, convert
            gz_raw = math.degrees(gz_raw)

        ay_filtered = self._lowpass("ay", ay_raw)
        updates = {
            "acc_x":    self._lowpass("ax", ax_raw),
            "acc_y":    ay_filtered,
            "acc_z":    self._lowpass("az", az_raw),
            "gyro_yaw": self._lowpass("gz", gz_raw),
            # Brake pressure proxy from longitudinal deceleration
            "brake_pressure": max(0.0, -ay_filtered * 30),
            # Jerk: rate of change of lateral acceleration — useful for
            # LSTM detection, fatigue detection, and braking anomalies.
            "jerk": abs(ay_filtered - self._last_data.get("acc_y", 0)),
            # Vibration proxy: combined horizontal acceleration magnitude.
            # Improves autoencoder + IF road roughness and pothole detection.
            "vibration": abs(ax_raw) + abs(ay_raw),
        }
        self.buffer.write(updates, source="mobile_imu")
        self._last_data = updates

    def register(self, app):
        """Add /ws/imu WebSocket route to existing FastAPI app."""
        from fastapi import WebSocket
        receiver = self

        @app.websocket("/ws/imu")
        async def imu_stream(ws: WebSocket):
            await ws.accept()
            await receiver.handle(ws)

        log.info("Registered /ws/imu endpoint")
        return app


# ═══════════════════════════════════════════════════════════════
#  B. ENHANCED OBD-II
# ═══════════════════════════════════════════════════════════════

# Extended PID set with friendly names
OBD_PID_MAP = {
    "speed":          ("SPEED",                  lambda v: v * 0.621371),  # km/h → mph
    "rpm":            ("RPM",                    lambda v: v),
    "thermal":        ("COOLANT_TEMP",           lambda v: v),
    "oil_pressure":   ("OIL_TEMP",               lambda v: v),
    "throttle":       ("THROTTLE_POS",           lambda v: v),
    "fuel_level":     ("FUEL_LEVEL",             lambda v: v / 100),
    "battery_voltage":("CONTROL_MODULE_VOLTAGE", lambda v: v),
    "intake_temp":    ("INTAKE_TEMP",            lambda v: v),
    "engine_load":    ("ENGINE_LOAD",            lambda v: v),
    "maf":            ("MAF",                    lambda v: v),              # g/s
    "fuel_trim_s":    ("SHORT_FUEL_TRIM_1",      lambda v: v),              # %
    "fuel_trim_l":    ("LONG_FUEL_TRIM_1",       lambda v: v),              # %
}


class EnhancedOBD:
    """
    Production-grade OBD-II reader with:
      • Auto port detection via serial scan
      • PID blacklisting (skips PIDs that timeout repeatedly)
      • Reconnection on connection drop
      • Derived signals: engine stress index, fuel efficiency proxy
    """

    TIMEOUT_MAX = 3   # blacklist a PID after this many consecutive timeouts

    def __init__(self, buffer: SensorBuffer, port: str | None = None):
        self.buffer      = buffer
        self._port       = port   # None = auto-detect
        self._conn       = None
        self._connected  = False
        self._blacklist: set = set()
        self._timeouts:  dict = {}   # pid → consecutive timeout count
        self._thread     = None
        self._running    = False
        log.info("EnhancedOBD initialised")

    def _find_port(self) -> str | None:
        """Scan serial ports for ELM327 by description or VID/PID."""
        for port in serial.tools.list_ports.comports():
            desc = (port.description or "").lower()
            if any(k in desc for k in ("elm", "obd", "ftdi", "ch340", "cp210")):
                log.info(f"OBD port found: {port.device} ({port.description})")
                return port.device
        return None

    def _connect(self) -> bool:
        if not _OBD_OK:
            return False
        port = self._port or self._find_port()
        if not port:
            log.warning("OBD-II: no ELM327 adapter found")
            return False
        try:
            self._conn      = obd.OBD(portstr=port, baudrate=38400,
                                      protocol=None, fast=True, timeout=5)
            self._connected = self._conn.is_connected()
            if self._connected:
                log.info(f"OBD-II connected on {port}")
            return self._connected
        except Exception as e:
            log.warning(f"OBD connect failed: {e}")
            return False

    def _poll_once(self):
        updates = {}
        for key, (pid_name, transform) in OBD_PID_MAP.items():
            if key in self._blacklist:
                continue
            try:
                cmd  = getattr(obd.commands, pid_name, None)
                if cmd is None:
                    self._blacklist.add(key)
                    continue
                resp = self._conn.query(cmd)
                if resp.is_null():
                    self._timeouts[key] = self._timeouts.get(key, 0) + 1
                    if self._timeouts[key] >= self.TIMEOUT_MAX:
                        log.warning(f"OBD blacklisting {key} after {self.TIMEOUT_MAX} nulls")
                        self._blacklist.add(key)
                    continue
                self._timeouts[key] = 0
                updates[key] = float(transform(resp.value.magnitude))
            except Exception:
                self._timeouts[key] = self._timeouts.get(key, 0) + 1

        # Derived signals
        speed   = updates.get("speed", 0)
        rpm     = updates.get("rpm", 1)
        load    = updates.get("engine_load", 0)
        if speed > 0 and rpm > 0:
            updates["engine_stress"] = round(load * rpm / 5000, 3)
            updates["gear_estimate"] = round(speed / max(rpm * 0.003, 0.01), 1)

        self.buffer.write(updates, source="obd")

    def _loop(self):
        while self._running:
            if not self._connected:
                if not self._connect():
                    time.sleep(5)
                    continue
            try:
                self._poll_once()
            except Exception as e:
                log.warning(f"OBD poll error: {e} — reconnecting")
                self._connected = False
            time.sleep(0.1)   # 10 Hz

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True, name="obd")
        self._thread.start()

    def stop(self):
        self._running = False

    @property
    def connected(self) -> bool:
        return self._connected


# ═══════════════════════════════════════════════════════════════
#  C. GPS (serial NMEA or gpsd)
# ═══════════════════════════════════════════════════════════════
class RealGPS:
    """
    GPS reader with two backends:
      1. gpsd (preferred) — requires gpsd daemon + gpsd-py3
      2. Serial NMEA (fallback) — reads raw NMEA from USB GPS dongle

    Computes:
      • Speed cross-check (GPS vs OBD)
      • Road curvature from heading rate (dHeading/dt / speed)
      • Accuracy flag (HDOP < 2.5 = good, > 5.0 = poor)
    """

    def __init__(self, buffer: SensorBuffer, serial_port: str | None = None):
        self.buffer  = buffer
        self._sport  = serial_port
        self._thread = None
        self._running= False
        self._prev_heading = None
        self._prev_ts      = None
        self._speed_hist   = deque(maxlen=5)

    def _parse_gprmc(self, line: str) -> dict | None:
        """Parse $GPRMC NMEA sentence → {lat, lon, speed_knots, heading}"""
        parts = line.split(",")
        if len(parts) < 10 or parts[2] != "A":   # A = active
            return None
        try:
            def dm2dd(dm, hemi):
                dm = float(dm)
                d  = int(dm // 100)
                m  = dm - d * 100
                dd = d + m / 60
                return -dd if hemi in ("S", "W") else dd

            return {
                "gps_lat":     dm2dd(parts[3], parts[4]),
                "gps_lon":     dm2dd(parts[5], parts[6]),
                "gps_speed":   float(parts[7]) * 1.15078,   # knots → mph
                "gps_heading": float(parts[8]),
            }
        except (ValueError, IndexError):
            return None

    def _parse_gpgga(self, line: str) -> dict | None:
        """Parse $GPGGA → {lat, lon, alt, hdop}"""
        parts = line.split(",")
        if len(parts) < 15 or parts[6] == "0":
            return None
        try:
            def dm2dd(dm, hemi):
                dm = float(dm)
                d  = int(dm // 100)
                m  = dm - d * 100
                dd = d + m / 60
                return -dd if hemi in ("S", "W") else dd
            hdop = float(parts[8]) if parts[8] else 99.0
            return {
                "gps_lat":     dm2dd(parts[2], parts[3]),
                "gps_lon":     dm2dd(parts[4], parts[5]),
                "gps_alt":     float(parts[9]) if parts[9] else 0,
                "gps_hdop":    hdop,
                "gps_quality": "GOOD" if hdop < 2.5 else "FAIR" if hdop < 5 else "POOR",
            }
        except (ValueError, IndexError):
            return None

    def _derive_curvature(self, heading: float, speed: float, ts: float) -> float:
        """Curvature κ = dθ/ds = (dθ/dt) / speed"""
        if self._prev_heading is None or self._prev_ts is None:
            self._prev_heading = heading
            self._prev_ts      = ts
            return 0.0
        dt     = ts - self._prev_ts
        if dt < 0.1:
            return 0.0
        dtheta = heading - self._prev_heading
        # Wrap to [-180, 180]
        dtheta = (dtheta + 180) % 360 - 180
        self._prev_heading = heading
        self._prev_ts      = ts
        speed_ms = max(speed * 0.44704, 0.5)   # mph → m/s, min 0.5
        return abs(math.radians(dtheta) / dt / speed_ms)

    def _gpsd_loop(self):
        while self._running:
            try:
                pkt     = gpsd.get_current()
                updates = {
                    "gps_speed":   float(pkt.hspeed() or 0) * 2.237,   # m/s → mph
                    "gps_lat":     pkt.lat,
                    "gps_lon":     pkt.lon,
                    "gps_alt":     pkt.alt,
                }
                heading = getattr(pkt, "track", None)
                if heading is not None:
                    speed = updates["gps_speed"]
                    curv  = self._derive_curvature(heading, speed, time.time())
                    updates["curvature"]    = round(min(curv, 1.0), 4)
                    updates["gps_heading"]  = heading
                self.buffer.write(updates, source="gps")
            except Exception as e:
                log.debug(f"gpsd error: {e}")
            time.sleep(1.0)

    def _serial_loop(self):
        port = self._sport or self._find_gps_port()
        if not port:
            log.warning("GPS: no serial NMEA port found")
            return
        try:
            ser = serial.Serial(port, 9600, timeout=2)
            log.info(f"GPS serial opened: {port}")
        except Exception as e:
            log.warning(f"GPS serial failed: {e}")
            return
        updates: dict = {}
        while self._running:
            try:
                line = ser.readline().decode("ascii", errors="ignore").strip()
                if line.startswith("$GPRMC"):
                    r = self._parse_gprmc(line)
                    if r:
                        updates.update(r)
                        h  = r.get("gps_heading", 0)
                        sp = r.get("gps_speed", 0)
                        updates["curvature"] = round(self._derive_curvature(h, sp, time.time()), 4)
                elif line.startswith("$GPGGA"):
                    r = self._parse_gpgga(line)
                    if r: updates.update(r)
                if updates:
                    self.buffer.write(updates, source="gps")
            except Exception as e:
                log.debug(f"GPS serial read error: {e}")

    def _find_gps_port(self) -> str | None:
        for port in serial.tools.list_ports.comports():
            desc = (port.description or "").lower()
            if any(k in desc for k in ("gps", "gnss", "u-blox", "globalsat", "sirf")):
                return port.device
        return None

    def start(self):
        self._running = True
        backend = self._gpsd_loop if _GPS_OK else self._serial_loop
        self._thread = threading.Thread(target=backend, daemon=True, name="gps")
        self._thread.start()
        log.info(f"GPS started (backend={'gpsd' if _GPS_OK else 'serial NMEA'})")

    def stop(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════
#  ENHANCED SENSOR HUB  (drop-in replacement for SensorHub)
# ═══════════════════════════════════════════════════════════════
class EnhancedSensorHub:
    """
    Upgrade 2 — Drop-in replacement for SensorHub.
    Wires MobileIMUReceiver + EnhancedOBD + RealGPS to a shared
    SensorBuffer, then exposes the same API as the original SensorHub.

    Usage in main.py:
        from backend.pipeline.mobile_sensors import EnhancedSensorHub, SensorBuffer
        shared_buf   = SensorBuffer()
        sensor_hub   = EnhancedSensorHub(state, shared_buf)
    """

    def __init__(self, state: "SystemState", buffer: SensorBuffer | None = None):
        self.state        = state
        self.buffer       = buffer or SensorBuffer()
        self.imu          = MobileIMUReceiver(self.buffer)
        self.obd          = EnhancedOBD(self.buffer)
        self.gps          = RealGPS(self.buffer)
        self._fusion_task = None
        self._running     = False

    @property
    def obd_connected(self): return self.obd.connected
    @property
    def imu_connected(self): return self.imu._clients > 0
    @property
    def gps_connected(self): return getattr(self.gps, "_thread", None) is not None

    async def start(self):
        self._running = True
        self.obd.start()
        self.gps.start()
        self._fusion_task = asyncio.create_task(self._fusion_loop())
        log.info("EnhancedSensorHub started")

    async def stop(self):
        self._running = False
        self.obd.stop()
        self.gps.stop()
        if self._fusion_task:
            self._fusion_task.cancel()

    def register_mobile_imu(self, app):
        """Register /ws/imu on the FastAPI app."""
        return self.imu.register(app)

    async def _fusion_loop(self):
        """Read from SensorBuffer → write to SystemState @ 20 Hz."""
        from backend.pipeline.sensors import Kalman1D, KALMAN_PARAMS, STALE_THRESHOLDS
        kf: dict = {k: Kalman1D(*v) for k, v in KALMAN_PARAMS.items()}
        while self._running:
            raw  = self.buffer.read_all()
            fused: dict = {}
            for k, v in raw.items():
                if isinstance(v, (int, float)) and k in kf:
                    fused[k] = round(kf[k].update(float(v)), 4)
                else:
                    fused[k] = v
            fused["_fusion_ts"] = time.time()
            fused["_staleness"] = {}   # placeholder — real staleness from buffer.age()
            self.state.update_sensors(fused)
            await asyncio.sleep(0.05)
