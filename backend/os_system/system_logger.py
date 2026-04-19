import json
import os
import threading
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "system_log.jsonl"
MAX_SIZE_MB = 5  # rotate after 5MB

LOG_DIR.mkdir(exist_ok=True)

_lock = threading.Lock()


# ---------------------------------------------------------
# 🔄 LOG ROTATION
# ---------------------------------------------------------
def rotate_logs():
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_SIZE_MB * 1024 * 1024:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        LOG_FILE.rename(LOG_DIR / f"system_log_{timestamp}.jsonl")


# ---------------------------------------------------------
# 🧠 SAFE SERIALIZATION
# ---------------------------------------------------------
def safe_json(data):
    try:
        return json.dumps(data)
    except Exception:
        return json.dumps({"error": "serialization_failed"})


# ---------------------------------------------------------
# 📝 MAIN LOGGER
# ---------------------------------------------------------
def log_event(payload, level="INFO"):

    try:
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "data": payload
        }

        with _lock:  # thread-safe
            rotate_logs()

            with open(LOG_FILE, "a") as f:
                f.write(safe_json(entry) + "\n")
                f.flush()  # 🔥 ensure write

    except Exception as e:
        print("Logging failed:", e)


# ---------------------------------------------------------
# 🚨 SHORTCUT HELPERS
# ---------------------------------------------------------
def log_info(data):
    log_event(data, "INFO")


def log_warning(data):
    log_event(data, "WARNING")


def log_error(data):
    log_event(data, "ERROR")
