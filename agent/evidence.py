from datetime import datetime, timezone

STALE_THRESHOLD = 300


def _refuse(reason: str, message: str):
    return {
        "mode": "refuse",
        "reason": reason,
        "text": message,
        "confidence": 0.0,
        "evidence": "insufficient telemetry",
    }


def check_evidence(domains, intent, facts: dict):
    """
    Evidence gate used by agent_core.
    Signature MUST match agent_core:
        check_evidence(domains, intent, facts)
    """

    # ---------------- Timestamp freshness ----------------

    meta = facts.get("metadata", {})
    ts_raw = meta.get("collected_at")

    if ts_raw:
        ts = datetime.fromisoformat(ts_raw)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > STALE_THRESHOLD:
            return _refuse("evidence", "telemetry stale")

    # ---------------- Metrics presence ----------------

    metrics = facts.get("metrics") or {}
    probes = facts.get("probes") or {}

    if not metrics:
        return _refuse("domain", "no metrics present")

    # ---------------- Probe sanity ----------------

    if probes:
        usable = [v for v in probes.values() if v == "ok"]
        if not usable:
            return _refuse("domain", "no usable probes")

    # ---------------- CPU + Memory minimum ----------------

    cpu = metrics.get("cpu")
    mem = metrics.get("memory")

    if not cpu or not mem:
        return _refuse("domain", "missing cpu/memory")

    if cpu.get("usage") is None and cpu.get("usage_percent") is None:
        return _refuse("domain", "cpu missing usage")

    if mem.get("usage") is None and mem.get("percent") is None:
        return _refuse("domain", "memory missing usage")

    # ---------------- PASS ----------------

    return {
        "mode": "ok",
        "confidence": 0.85,
        "evidence": "live telemetry",
    }
