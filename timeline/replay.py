import json
from pathlib import Path

HISTORY_DIR = Path("system_state/history")

def replay(date_prefix: str):
    files = sorted(
        HISTORY_DIR.glob(f"{date_prefix}*.json")
    )

    if not files:
        print("No records found for the given date.")
        return

    for file in files:
        with open(file) as f:
            data = json.load(f)

        print("\n--------------------------------")
        print(f"Time     : {data['timestamp']}")
        print(f"Posture  : {data['posture']['posture']}")

        judgments = data.get("judgments", [])
        if judgments:
            print("Judgments:")
            for j in judgments:
                print(
                    f"  - {j['state']} "
                    f"(confidence {j['confidence']:.2f})"
                )
        else:
            print("Judgments: none")

        input("\nPress Enter to continue...")
