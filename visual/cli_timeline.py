import json
from pathlib import Path
from datetime import datetime

HISTORY_DIR = Path("system_state/history")

SYMBOLS = {
    "idle-capable": "█",
    "work-stable": "▓",
    "performance-sensitive": "▒",
    "capacity-constrained": "░",
}


def render_today_timeline():
    if not HISTORY_DIR.exists():
        print("No timeline data available.")
        return

    files = sorted(HISTORY_DIR.glob("*.json"))
    if not files:
        print("No timeline data available.")
        return

    print("\nToday (UTC)\n")

    rendered = 0

    for f in files:
        try:
            if f.stat().st_size == 0:
                continue  # skip empty files safely

            with open(f) as fh:
                r = json.load(fh)

            ts = r.get("timestamp")
            posture = r.get("posture", {}).get("posture", "unknown")

            time = datetime.fromisoformat(
                ts.replace("Z", "")
            ).strftime("%H:%M")

            symbol = SYMBOLS.get(posture, "?")
            print(f"{time} ├─ {symbol} {posture}")
            rendered += 1

        except Exception:
            # Skip malformed / partial files silently
            continue

    if rendered == 0:
        print("No valid timeline entries available.")
        return

    print("\nLegend:")
    for k, v in SYMBOLS.items():
        print(f"{v} {k}")
