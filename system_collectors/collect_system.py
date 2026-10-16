import json
import platform
import socket
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from system_collectors.factory import get_collector

OUTPUT_PATH = Path("system_facts/current.json")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

def main():
    collector = get_collector()
    facts = collector.collect_all()

    sample = {
        "schema_version": "1.0",
        "device": {
            "hostname": socket.gethostname(),
            "os": platform.system().lower(),
            "platform": platform.platform()
        },
        "timestamp": time.time(),
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data_quality": {
            "fresh": True,
            "missing": []
        },
        "facts": facts
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(sample, f, indent=2)

    print("System telemetry collected successfully.")

if __name__ == "__main__":
    main()
