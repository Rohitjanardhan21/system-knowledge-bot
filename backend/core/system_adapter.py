"""
OS-agnostic metric collection.
All platform differences are isolated here.
The rest of the system never touches psutil or platform APIs directly.
"""
import platform
import psutil

OS = platform.system()  # "Linux", "Windows", "Darwin"

FAILURE_TYPES = {
    "SIGILL":                      "CPU_INSTRUCTION_UNSUPPORTED",
    "STATUS_ILLEGAL_INSTRUCTION":  "CPU_INSTRUCTION_UNSUPPORTED",
    "EXC_BAD_INSTRUCTION":         "CPU_INSTRUCTION_UNSUPPORTED",
    "MemoryError":                 "MEMORY_EXHAUSTION",
    "OSError":                     "DISK_IO_SATURATION",
    "ConnectionError":             "NETWORK_DEGRADATION",
    "BrokenPipeError":             "PROCESS_CRASH",
}

def get_metrics() -> dict:
    """Returns normalized metrics regardless of OS."""
    cpu = psutil.cpu_percent(interval=0.05)
    mem = psutil.virtual_memory().percent

    # Disk — Linux uses /proc, Windows uses C:\, macOS uses /
    try:
        io = psutil.disk_io_counters()
        disk = min(100, (io.read_bytes + io.write_bytes) / 1e8 * 5) if io else 0.0
    except Exception:
        disk = psutil.disk_usage('/').percent if OS != "Windows" else psutil.disk_usage('C:\\').percent

    # Network — normalized across platforms
    try:
        net_io = psutil.net_io_counters()
        net = min(100, (net_io.bytes_sent + net_io.bytes_recv) / 1e8 * 10)
    except Exception:
        net = 0.0

    health = max(0, 100 - max(0, cpu - 70) * 0.35 - max(0, mem - 60) * 0.25)

    return {
        "cpu_percent":     round(float(cpu),    2),
        "memory":          round(float(mem),    2),
        "disk_percent":    round(float(disk),   2),
        "network_percent": round(float(net),    2),
        "health_score":    round(float(health), 2),
        "os":              OS,
    }

def get_processes() -> list:
    """Returns top processes normalized across OS."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            if p.info["status"] in ("zombie", "dead"):
                continue
            procs.append({
                "pid":  p.info["pid"],
                "name": (p.info["name"] or "unknown")[:24],
                "cpu":  round(p.info["cpu_percent"] or 0.0, 2),
                "mem":  round(p.info["memory_percent"] or 0.0, 2),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return procs

def classify_failure(raw_signal: str) -> dict:
    """Normalize OS-specific error signals into universal failure types."""
    for pattern, failure_type in FAILURE_TYPES.items():
        if pattern.lower() in raw_signal.lower():
            return {
                "failure_type": failure_type,
                "severity":     "HIGH",
                "confidence":   0.92,
                "raw_signal":   raw_signal,
                "os":           OS,
            }
    return {
        "failure_type": "UNKNOWN",
        "severity":     "MEDIUM",
        "confidence":   0.50,
        "raw_signal":   raw_signal,
        "os":           OS,
    }
