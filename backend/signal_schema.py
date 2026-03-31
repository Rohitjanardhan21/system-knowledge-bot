# ---------------------------------------------------------
# 🧠 SIGNAL SCHEMA (MULTI-MODAL NORMALIZATION LAYER)
# ---------------------------------------------------------

from datetime import datetime
from typing import Dict, Any


# ---------------------------------------------------------
# DEFAULT SAFE VALUES
# ---------------------------------------------------------
DEFAULTS = {
    "acoustic": [],
    "thermal": 0.0,
    "vibration": [],
    "electrical": 0.0,
    "compute": 0.0
}


# ---------------------------------------------------------
# 🔧 HELPERS
# ---------------------------------------------------------

def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def safe_list(value):
    if isinstance(value, list):
        return value
    return []


def normalize_timestamp(ts):
    """
    Ensures ISO 8601 timestamp
    """
    if not ts:
        return datetime.utcnow().isoformat()

    if isinstance(ts, (int, float)):
        return datetime.utcfromtimestamp(ts).isoformat()

    if isinstance(ts, str):
        return ts

    return datetime.utcnow().isoformat()


# ---------------------------------------------------------
# 🔥 MAIN FUNCTION
# ---------------------------------------------------------

def build_signal_packet(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts ANY raw input into a standardized multi-modal signal packet.

    Supports:
    - system metrics (CPU, memory)
    - sensor inputs (audio, vibration, thermal)
    - future industrial integrations

    Returns:
    Standardized signal packet
    """

    # -----------------------------------------------------
    # TIMESTAMP
    # -----------------------------------------------------
    timestamp = normalize_timestamp(
        raw.get("time") or raw.get("timestamp")
    )

    # -----------------------------------------------------
    # SIGNAL EXTRACTION (FLEXIBLE INPUT SUPPORT)
    # -----------------------------------------------------

    signals = {
        # 🔊 AUDIO / SOUND
        "acoustic": safe_list(
            raw.get("audio")
            or raw.get("sound")
            or raw.get("acoustic")
            or DEFAULTS["acoustic"]
        ),

        # 🌡️ TEMPERATURE
        "thermal": safe_float(
            raw.get("temp")
            or raw.get("temperature")
            or raw.get("thermal")
            or raw.get("cpu_temp")
            or DEFAULTS["thermal"]
        ),

        # 📳 VIBRATION
        "vibration": safe_list(
            raw.get("vibration")
            or raw.get("imu")
            or raw.get("accelerometer")
            or DEFAULTS["vibration"]
        ),

        # ⚡ ELECTRICAL
        "electrical": safe_float(
            raw.get("current")
            or raw.get("voltage")
            or raw.get("power")
            or DEFAULTS["electrical"]
        ),

        # 💻 COMPUTE LOAD
        "compute": safe_float(
            raw.get("cpu")
            or raw.get("cpu_pct")
            or raw.get("compute")
            or DEFAULTS["compute"]
        ),
    }

    # -----------------------------------------------------
    # CONTEXT + DEVICE INFO
    # -----------------------------------------------------

    context = raw.get("context", "unknown")

    device_type = raw.get(
        "device_type",
        infer_device_type(signals)
    )

    # -----------------------------------------------------
    # VALIDATION FLAGS
    # -----------------------------------------------------

    validity = {
        "has_acoustic": len(signals["acoustic"]) > 0,
        "has_vibration": len(signals["vibration"]) > 0,
        "has_thermal": signals["thermal"] > 0,
        "has_electrical": signals["electrical"] > 0,
        "has_compute": signals["compute"] > 0
    }

    # -----------------------------------------------------
    # FINAL PACKET
    # -----------------------------------------------------

    return {
        "timestamp": timestamp,
        "signals": signals,
        "context": context,
        "device_type": device_type,
        "validity": validity
    }


# ---------------------------------------------------------
# 🧠 DEVICE TYPE INFERENCE (SMART DEFAULT)
# ---------------------------------------------------------

def infer_device_type(signals: Dict[str, Any]) -> str:
    """
    Infers device type based on available signals
    """

    if signals["acoustic"] and signals["vibration"]:
        return "mechanical_system"

    if signals["thermal"] > 0 and signals["compute"] > 0:
        return "compute_device"

    if signals["electrical"] > 0:
        return "electrical_system"

    return "generic_system"


# ---------------------------------------------------------
# 🧪 DEBUG / TEST
# ---------------------------------------------------------

if __name__ == "__main__":

    sample_input = {
        "cpu": 75,
        "temp": 82,
        "audio": [0.2, 0.5, 0.3],
        "vibration": [0.1, 0.2, 0.15],
        "current": 12,
        "time": 1710000000
    }

    packet = build_signal_packet(sample_input)

    from pprint import pprint
    pprint(packet)
