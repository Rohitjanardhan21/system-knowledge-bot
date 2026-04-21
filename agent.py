"""
CVIS Universal Agent
Runs on any device (Linux/Windows/macOS)
Pushes metrics to central CVIS server every 5 seconds

Usage:
    python3 agent.py --server http://your-server:8000 --key your-api-key
    python3 agent.py --server http://your-server:8000 --key your-api-key --device myserver-01
"""
import argparse
import platform
import socket
import time
import uuid
import json
import urllib.request
import urllib.error

# ── Optional psutil ───────────────────────────────────────
try:
    import psutil
    PS_OK = True
except ImportError:
    PS_OK = False

OS = platform.system()  # Linux / Windows / Darwin

def get_device_id():
    """Stable device ID — persisted locally so it survives restarts."""
    id_file = ".cvis_device_id"
    try:
        with open(id_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        device_id = uuid.uuid4().hex[:12]
        with open(id_file, "w") as f:
            f.write(device_id)
        return device_id

def collect_metrics():
    """Collect metrics — works on any OS via psutil."""
    if not PS_OK:
        import math
        t = time.time()
        return {
            "cpu_percent":     round(30 + 20 * abs(math.sin(t / 60)), 2),
            "memory":          round(45 + 10 * abs(math.sin(t / 90)), 2),
            "disk_percent":    round(25 +  5 * abs(math.sin(t / 120)), 2),
            "network_percent": round(30 + 15 * abs(math.sin(t / 45)), 2),
            "health_score":    85.0,
            "simulated":       True,
        }

    cpu  = psutil.cpu_percent(interval=0.1)
    mem  = psutil.virtual_memory().percent

    try:
        io   = psutil.disk_io_counters()
        disk = min(100, (io.read_bytes + io.write_bytes) / 1e8 * 5) if io else 0.0
    except Exception:
        try:
            path = "C:\\" if OS == "Windows" else "/"
            disk = psutil.disk_usage(path).percent
        except Exception:
            disk = 0.0

    try:
        net_io = psutil.net_io_counters()
        net    = min(100, (net_io.bytes_sent + net_io.bytes_recv) / 1e8 * 10)
    except Exception:
        net = 0.0

    health = max(0, 100 - max(0, cpu - 70) * 0.35 - max(0, mem - 60) * 0.25)

    return {
        "cpu_percent":     round(float(cpu),    2),
        "memory":          round(float(mem),    2),
        "disk_percent":    round(float(disk),   2),
        "network_percent": round(float(net),    2),
        "health_score":    round(float(health), 2),
        "simulated":       False,
    }

def collect_processes():
    """Top processes by CPU — works cross-platform."""
    if not PS_OK:
        return []
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
    return sorted(procs, key=lambda x: x["cpu"], reverse=True)[:10]

def push_metrics(server, api_key, device_id, device_name, payload):
    """Send metrics to CVIS server. Uses only stdlib — no requests needed."""
    url = f"{server}/devices/{device_id}/metrics"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key":    api_key,
            "X-Device-ID":  device_id,
            "X-Device-Name":device_name,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        print(f"[CVIS] Server error {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"[CVIS] Cannot reach server: {e.reason}")
        return False

def main():
    parser = argparse.ArgumentParser(description="CVIS Universal Agent")
    parser.add_argument("--server",   required=True, help="CVIS server URL e.g. http://192.168.1.10:8000")
    parser.add_argument("--key",      required=True, help="API key from CVIS server")
    parser.add_argument("--device",   default=None,  help="Device name (default: hostname)")
    parser.add_argument("--interval", default=5,     type=int, help="Push interval in seconds (default: 5)")
    args = parser.parse_args()

    device_id   = get_device_id()
    device_name = args.device or socket.gethostname()
    server      = args.server.rstrip("/")

    print(f"[CVIS] Agent starting")
    print(f"[CVIS] Device:   {device_name} ({device_id})")
    print(f"[CVIS] OS:       {OS} {platform.release()}")
    print(f"[CVIS] Server:   {server}")
    print(f"[CVIS] Interval: {args.interval}s")
    print(f"[CVIS] psutil:   {'available' if PS_OK else 'missing — using simulation'}")
    if not PS_OK:
        print("[CVIS] Install psutil for real metrics: pip install psutil")
    print()

    consecutive_failures = 0

    while True:
        try:
            metrics  = collect_metrics()
            processes = collect_processes()

            import shutil
    cpu_count   = psutil.cpu_count() if PS_OK else 1
    ram_gb      = round(psutil.virtual_memory().total / 1e9, 1) if PS_OK else 0
    disk_gb     = round(psutil.disk_usage("/").total / 1e9, 1) if PS_OK and OS != "Windows" else 0
    device_type = ("windows-pc" if OS == "Windows" else
                   "mac" if OS == "Darwin" else
                   "k8s-node" if shutil.which("kubectl") else
                   "docker-host" if shutil.which("docker") else
                   "embedded-linux" if (psutil.cpu_count() or 1) <= 2 and ram_gb <= 4 else
                   "linux-server")
    payload = {
                "device_id":   device_id,
                "device_name": device_name,
                "os":          OS,
                "os_version":  platform.release(),
                "hostname":    socket.gethostname(),
                "arch":        platform.machine(),
                "cpu_count":   cpu_count,
                "ram_gb":      ram_gb,
                "disk_gb":     disk_gb,
                "device_type": device_type,
                "python":      platform.python_version(),
                "timestamp":   time.time(),
                "metrics":     metrics,
                "processes":   processes,
            }

            ok = push_metrics(server, args.key, device_id, device_name, payload)

            if ok:
                consecutive_failures = 0
                status = f"cpu={metrics['cpu_percent']}% mem={metrics['memory']}% health={metrics['health_score']}%"
                print(f"[CVIS] ✓ {time.strftime('%H:%M:%S')} {status}")
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print(f"[CVIS] ✗ Server unreachable — will keep retrying every {args.interval}s")

        except KeyboardInterrupt:
            print("\n[CVIS] Agent stopped.")
            break
        except Exception as e:
            print(f"[CVIS] Error: {e}")

        time.sleep(args.interval)

if __name__ == "__main__":
    main()
