from datetime import datetime, timezone

def is_fresh(metadata):
    collected_at = metadata.get("collected_at")
    ttl = metadata.get("ttl_seconds", 0)

    if not collected_at:
        return False

    collected_time = datetime.fromisoformat(collected_at).replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - collected_time).total_seconds()

    return age <= ttl
