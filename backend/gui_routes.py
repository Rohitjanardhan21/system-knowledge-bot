from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter(prefix="/gui", tags=["gui"])

# IMPORTANT:
# Uvicorn must be started from the project root so these paths resolve correctly
STATE_DIR = Path("system_state")
LATEST_FILE = STATE_DIR / "latest.json"
HISTORY_DIR = STATE_DIR / "history"


@router.get("/current")
def get_current_state():
    """
    Returns the current system state for the GUI.

    Contract:
    - Always explicit
    - Never lies
    - Never assumes state exists
    """

    if not LATEST_FILE.exists():
        return {
            "available": False,
            "reason": "System state not yet collected"
        }

    try:
        with open(LATEST_FILE, "r") as f:
            state = json.load(f)
    except Exception as e:
        return {
            "available": False,
            "reason": f"Failed to read system state: {str(e)}"
        }

    # Minimal sanity check (do NOT over-validate here)
    if "posture" not in state:
        return {
            "available": False,
            "reason": "System state incomplete (missing posture)"
        }

    return {
        "available": True,
        "state": state
    }


@router.get("/timeline")
def get_posture_timeline(limit: int = 100):
    """
    Returns posture history for the GUI timeline.

    Rules:
    - Read-only
    - Posture-only
    - Safe if history is empty
    - Never crashes on bad files
    """

    if not HISTORY_DIR.exists():
        return []

    files = sorted(HISTORY_DIR.glob("*.json"))

    timeline = []

    for file in files[-limit:]:
        try:
            with open(file, "r") as f:
                record = json.load(f)

            posture = record.get("posture", {}).get("posture")
            timestamp = record.get("timestamp")

            if posture and timestamp:
                timeline.append({
                    "timestamp": timestamp,
                    "posture": posture
                })

        except Exception:
            # Corrupt history must never break the GUI
            continue

    return timeline
