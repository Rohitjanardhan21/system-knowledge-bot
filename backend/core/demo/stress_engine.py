"""
CVIS Stress Test Engine
Controlled stress scenarios for demo and ML training.
Safe ceilings on all metrics — will not crash the machine.
"""
import threading
import time
import os
import sys

_lock = threading.Lock()
_active_stress: dict = {}   # scenario_id -> thread + stop_event
_stress_log: list = []      # history of stress runs


# ── Safety ceilings ───────────────────────────────────────────────────────────
CPU_CEILING    = 85.0   # never push CPU above this %
MEMORY_CEILING = 82.0   # never push memory above this %
MAX_DURATION_S = 300    # max 5 minutes per scenario


def _get_current_memory_pct() -> float:
    try:
        import psutil
        return psutil.virtual_memory().percent
    except Exception:
        return 0.0


def _get_current_cpu_pct() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except Exception:
        return 0.0


# ── CPU stress worker ────────────────────────────────────────────────────────
def _cpu_stress_worker(stop_event: threading.Event, intensity: float = 0.75):
    """
    Burns CPU by doing math in a tight loop.
    intensity = fraction of time spent burning (0.0-1.0)
    Backs off automatically if CPU hits ceiling.
    """
    import math
    while not stop_event.is_set():
        if _get_current_cpu_pct() >= CPU_CEILING:
            time.sleep(0.5)
            continue
        # Burn for `intensity` fraction of each 100ms window
        burn_end = time.time() + 0.1 * intensity
        while time.time() < burn_end and not stop_event.is_set():
            _ = math.sqrt(sum(i * i for i in range(500)))
        # Rest for the remainder
        time.sleep(0.1 * (1.0 - intensity))


# ── Memory stress worker ─────────────────────────────────────────────────────
def _memory_stress_worker(stop_event: threading.Event, target_mb: int = 400):
    """
    Allocates memory in chunks up to target_mb.
    Releases immediately if memory hits ceiling.
    Always releases all memory on stop.
    """
    chunks = []
    chunk_size = 10 * 1024 * 1024  # 10MB chunks

    try:
        while not stop_event.is_set():
            mem_pct = _get_current_memory_pct()

            if mem_pct >= MEMORY_CEILING:
                # Release one chunk to stay below ceiling
                if chunks:
                    chunks.pop()
                time.sleep(0.5)
                continue

            current_mb = len(chunks) * 10
            if current_mb < target_mb:
                try:
                    chunks.append(bytearray(chunk_size))
                except MemoryError:
                    break
            time.sleep(0.3)
    finally:
        # Always release
        chunks.clear()


# ── Disk I/O stress worker ───────────────────────────────────────────────────
def _disk_stress_worker(stop_event: threading.Event):
    """
    Writes and reads a temp file repeatedly to spike disk I/O.
    Cleans up on stop.
    """
    tmp_path = '/tmp/cvis_stress_io.tmp'
    data = b'x' * (1024 * 1024)  # 1MB buffer
    try:
        while not stop_event.is_set():
            try:
                with open(tmp_path, 'wb') as f:
                    for _ in range(10):
                        f.write(data)
                with open(tmp_path, 'rb') as f:
                    f.read()
            except Exception:
                pass
            time.sleep(0.1)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


# ── Scenario definitions ─────────────────────────────────────────────────────
SCENARIOS = {
    "memory_pressure": {
        "id":          "memory_pressure",
        "label":       "Memory pressure",
        "description": "Gradually fills memory to trigger OOM prediction. Most dramatic for demos.",
        "duration_s":  180,
        "what_happens":"Memory climbs to ~80%. CVIS should predict OOM within 2-3 minutes.",
        "workers":     ["memory"],
        "target_mb":   400,
    },
    "cpu_spike": {
        "id":          "cpu_spike",
        "label":       "CPU spike",
        "description": "Pushes CPU to ~80% to trigger thermal/crash prediction.",
        "duration_s":  120,
        "what_happens":"CPU climbs to ~80%. CVIS should detect anomaly within 1-2 minutes.",
        "workers":     ["cpu"],
        "intensity":   0.75,
    },
    "combined": {
        "id":          "combined",
        "label":       "Combined stress",
        "description": "CPU + memory + disk simultaneously. Most likely to trigger a prediction fast.",
        "duration_s":  180,
        "what_happens":"All metrics spike together. CVIS ensemble score should exceed 0.7 within 90 seconds.",
        "workers":     ["cpu", "memory", "disk"],
        "intensity":   0.65,
        "target_mb":   300,
    },
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_scenarios() -> list:
    return list(SCENARIOS.values())


def start_scenario(scenario_id: str) -> dict:
    if scenario_id not in SCENARIOS:
        return {"success": False, "error": f"Unknown scenario: {scenario_id}"}

    with _lock:
        if scenario_id in _active_stress:
            return {"success": False, "error": "Scenario already running"}

    sc = SCENARIOS[scenario_id]
    duration = min(sc["duration_s"], MAX_DURATION_S)
    stop_event = threading.Event()
    threads = []

    if "cpu" in sc.get("workers", []):
        t = threading.Thread(
            target=_cpu_stress_worker,
            args=(stop_event, sc.get("intensity", 0.75)),
            daemon=True,
        )
        t.start()
        threads.append(t)

    if "memory" in sc.get("workers", []):
        t = threading.Thread(
            target=_memory_stress_worker,
            args=(stop_event, sc.get("target_mb", 400)),
            daemon=True,
        )
        t.start()
        threads.append(t)

    if "disk" in sc.get("workers", []):
        t = threading.Thread(
            target=_disk_stress_worker,
            args=(stop_event,),
            daemon=True,
        )
        t.start()
        threads.append(t)

    # Auto-stop after duration
    def _auto_stop():
        time.sleep(duration)
        stop_event.set()
        with _lock:
            _active_stress.pop(scenario_id, None)

    threading.Thread(target=_auto_stop, daemon=True).start()

    started_at = time.time()
    with _lock:
        _active_stress[scenario_id] = {
            "stop_event":  stop_event,
            "threads":     threads,
            "started_at":  started_at,
            "duration_s":  duration,
            "scenario_id": scenario_id,
        }
        _stress_log.append({
            "scenario_id": scenario_id,
            "label":       sc["label"],
            "started_at":  started_at,
            "duration_s":  duration,
        })

    return {
        "success":      True,
        "scenario_id":  scenario_id,
        "label":        sc["label"],
        "duration_s":   duration,
        "what_happens": sc["what_happens"],
        "started_at":   started_at,
    }


def stop_scenario(scenario_id: str) -> dict:
    with _lock:
        entry = _active_stress.pop(scenario_id, None)

    if not entry:
        # Try stopping all
        if scenario_id == "all":
            return stop_all()
        return {"success": False, "error": "Scenario not running"}

    entry["stop_event"].set()
    return {"success": True, "stopped": scenario_id}


def stop_all() -> dict:
    with _lock:
        ids = list(_active_stress.keys())
        for entry in _active_stress.values():
            entry["stop_event"].set()
        _active_stress.clear()
    return {"success": True, "stopped": ids}


def get_status() -> dict:
    now = time.time()
    with _lock:
        active = [
            {
                "scenario_id": sid,
                "label":       SCENARIOS.get(sid, {}).get("label", sid),
                "elapsed_s":   round(now - e["started_at"], 1),
                "remaining_s": max(0, round(e["duration_s"] - (now - e["started_at"]), 1)),
            }
            for sid, e in _active_stress.items()
        ]
    return {
        "running":      bool(active),
        "active":       active,
        "history_count": len(_stress_log),
    }
