from timeline.extractor import extract_posture_timeline

def posture_timeline_visual(day: str | None = None):
    events = extract_posture_timeline(day)

    if not events:
        return {
            "segments": [],
            "total_seconds": 0
        }

    segments = []
    total = 0

    # ---- normalize first event safely ----
    first = events[0]

    if isinstance(first, dict):
        last_time = first.get("timestamp")
        last_posture = first.get("posture")
    else:
        last_time, last_posture = first

    # ---- iterate remaining events ----
    for event in events[1:]:
        if isinstance(event, dict):
            ts = event.get("timestamp")
            posture = event.get("posture")
        else:
            ts, posture = event

        if posture != last_posture:
            duration = 10  # fixed sampling (safe default)
            segments.append({
                "posture": last_posture,
                "seconds": duration
            })
            total += duration
            last_posture = posture
            last_time = ts

    # ---- final segment ----
    segments.append({
        "posture": last_posture,
        "seconds": 10
    })
    total += 10

    return {
        "segments": segments,
        "total_seconds": total
    }
