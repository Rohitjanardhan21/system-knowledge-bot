from fastapi import APIRouter
from datetime import date
from timeline.durations import compute_posture_durations

router = APIRouter(prefix="/viz")

@router.get("/posture-today")
def posture_today(day: str | None = None):
    d = day or date.today().isoformat()
    data = compute_posture_durations(d)
    return {
        "day": d,
        "total_seconds": data["total_seconds"],
        "segments": data["segments"]
    }
