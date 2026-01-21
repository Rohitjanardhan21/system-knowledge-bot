import json
from pathlib import Path

from system_collectors.factory import get_collector

OUTPUT_PATH = Path("system_facts/current.json")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

def main():
    collector = get_collector()
    facts = collector.collect_all()

    with open(OUTPUT_PATH, "w") as f:
        json.dump(facts, f, indent=2)

    print("System facts collected successfully.")

if __name__ == "__main__":
    main()
