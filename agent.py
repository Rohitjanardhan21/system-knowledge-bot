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

    cpu  = psutil.cpu_percent(interval=0.5)
    mem  = psutil.virtual_memory().percent

    try:
        path = "C:\\" if OS == "Windows" else "/"
        disk = psutil.disk_usage(path).percent
    except Exception:
        disk = 0.0

    try:
        net_io = psutil.net_io_counters()
        if net_io:
            net = min(
                100.0,
                ((net_io.bytes_sent + net_io.bytes_recv) / 1e6)
            )
        else:
            net = 0.0
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

def identify_application(name):
    """Map a process executable to a stable application identity."""
    if not name:
        return "Unknown"

    name = name.lower()

    exact_map = {
        "chrome": "Chrome",
        "chromium": "Chromium",
        "firefox": "Firefox",
        "msedge": "Microsoft Edge",
        "edge": "Microsoft Edge",
        "brave": "Brave",
        "opera": "Opera",
        "code": "VS Code",
        "code-insiders": "VS Code",
        "python": "Python",
        "python3": "Python",
        "java": "Java",
        "node": "Node.js",
        "nodejs": "Node.js",
        "docker": "Docker",
        "dockerd": "Docker",
        "redis-server": "Redis",
        "nginx": "Nginx",
    }

    if name in exact_map:
        return exact_map[name]

    if "firefox" in name:
        return "Firefox"
    if "chrome" in name:
        return "Chrome"
    if "chromium" in name:
        return "Chromium"
    if "python" in name:
        return "Python"
    if "java" in name:
        return "Java"
    if "node" in name:
        return "Node.js"
    if "docker" in name:
        return "Docker"

    return name


def categorize_process(name):
    """Assign a broad process category."""
    if not name:
        return "system"

    name = name.lower()

    if any(x in name for x in (
        "chrome",
        "chromium",
        "firefox",
        "msedge",
        "edge",
        "brave",
        "opera",
    )):
        return "browser"

    if any(x in name for x in ("python", "java", "node")):
        return "runtime"

    if "docker" in name:
        return "container"

    return "system"


def collect_processes():
    """Top processes by CPU — works cross-platform."""
    if not PS_OK:
        return []

    procs = []

    for p in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_percent", "status"]
    ):
        try:
            if p.info["status"] in ("zombie", "dead"):
                continue

            name = (p.info["name"] or "unknown")[:24]

            procs.append({
                "pid": p.info["pid"],
                "name": name,
                "cpu": round(p.info["cpu_percent"] or 0.0, 2),
                "mem": round(p.info["memory_percent"] or 0.0, 2),
                "application": identify_application(name),
                "category": categorize_process(name),
            })

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return sorted(
        procs,
        key=lambda x: x["cpu"],
        reverse=True
    )[:10]

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
            metrics = collect_metrics()
            processes = collect_processes()

            import shutil

            cpu_count = psutil.cpu_count() if PS_OK else 1
            ram_gb = (
                round(psutil.virtual_memory().total / 1e9, 1)
                if PS_OK else 0
            )

            if PS_OK:
                try:
                    path = "C:\\" if OS == "Windows" else "/"
                    disk_gb = round(psutil.disk_usage(path).total / 1e9, 1)
                except Exception:
                    disk_gb = 0
            else:
                disk_gb = 0

            device_type = (
                "windows-pc" if OS == "Windows" else
                "mac" if OS == "Darwin" else
                "k8s-node" if shutil.which("kubectl") else
                "docker-host" if shutil.which("docker") else
                "embedded-linux"
                if (psutil.cpu_count() or 1) <= 2 and ram_gb <= 4
                else "linux-server"
            )

            payload = {
                "device_id": device_id,
                "device_name": device_name,
                "os": OS,
                "os_version": platform.release(),
                "hostname": socket.gethostname(),
                "arch": platform.machine(),
                "cpu_count": cpu_count,
                "ram_gb": ram_gb,
                "disk_gb": disk_gb,
                "device_type": device_type,
                "python": platform.python_version(),
                "timestamp": time.time(),
                "metrics": metrics,
                "processes": processes,
            }

            ok = push_metrics(
                server, args.key, device_id, device_name, payload
            )

            if ok:
                consecutive_failures = 0
                status = (
                    f"cpu={metrics['cpu_percent']}% "
                    f"mem={metrics['memory']}% "
                    f"health={metrics['health_score']}%"
                )
                print(
                    f"[CVIS] ✓ {time.strftime('%H:%M:%S')} {status}"
                )
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print(
                        f"[CVIS] ✗ Server unreachable — "
                        f"will keep retrying every {args.interval}s"
                    )

        except KeyboardInterrupt:
            print("\n[CVIS] Agent stopped.")
            break
        except Exception as e:
            print(f"[CVIS] Error: {e}")

        time.sleep(args.interval)

if __name__ == "__main__":
    main()
