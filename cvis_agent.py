"""
CVIS Universal Agent — clean rewrite
Runs on any OS, pushes metrics to CVIS server every 5 seconds
Usage: python3 cvis_agent.py --server http://IP:8000 --key test123 --device mypc
"""
import argparse, platform, socket, time, uuid, json, urllib.request, urllib.error, os, shutil

try:
    import psutil
    PS_OK = True
except ImportError:
    PS_OK = False

OS = platform.system()

def get_device_id():
    id_file = os.path.expanduser("~/.cvis_device_id")
    try:
        with open(id_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        did = uuid.uuid4().hex[:12]
        with open(id_file, "w") as f:
            f.write(did)
        return did

def collect_metrics():
    import math
    if not PS_OK:
        t = time.time()
        return {"cpu_percent": 30+20*abs(math.sin(t/60)), "memory": 45+10*abs(math.sin(t/90)),
                "disk_percent": 25+5*abs(math.sin(t/120)), "network_percent": 30+15*abs(math.sin(t/45)),
                "health_score": 85.0, "simulated": True}
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory().percent
    try:
        disk = psutil.disk_usage("C:\\" if OS == "Windows" else "/").percent
    except Exception:
        disk = 0.0
    try:
        n = psutil.net_io_counters()
        net = min(100, (n.bytes_sent + n.bytes_recv) / 1e8 * 10)
    except Exception:
        net = 0.0
    health = max(0, 100 - max(0, cpu-70)*0.35 - max(0, mem-60)*0.25)
    return {"cpu_percent": round(cpu,2), "memory": round(mem,2), "disk_percent": round(disk,2),
            "network_percent": round(net,2), "health_score": round(health,2), "simulated": False}

def collect_processes():
    if not PS_OK:
        return []
    procs = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_percent","status"]):
        try:
            if p.info["status"] in ("zombie","dead"):
                continue
            procs.append({"pid": p.info["pid"], "name": (p.info["name"] or "unknown")[:24],
                          "cpu": round(p.info["cpu_percent"] or 0.0, 2),
                          "mem": round(p.info["memory_percent"] or 0.0, 2)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(procs, key=lambda x: x["cpu"], reverse=True)[:10]

def detect_device_type():
    if OS == "Windows": return "windows-pc"
    if OS == "Darwin": return "mac"
    # kubectl check removed — Docker hosts often have kubectl installed
    if shutil.which("docker"): return "docker-host"
    if PS_OK and (psutil.cpu_count() or 1) <= 2 and psutil.virtual_memory().total < 4e9:
        return "embedded-linux"
    return "linux-server"

def push(server, key, device_id, name, payload):
    url = f"{server}/devices/{device_id}/metrics"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
          headers={"Content-Type":"application/json","X-API-Key":key,"X-Device-Name":name}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        print(f"[CVIS] Server error {e.code}")
        return False
    except urllib.error.URLError as e:
        print(f"[CVIS] Cannot reach server: {e.reason}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--device", default=None)
    parser.add_argument("--interval", default=5, type=int)
    args = parser.parse_args()

    device_id = get_device_id()
    device_name = args.device or socket.gethostname()
    server = args.server.rstrip("/")

    cpu_count = psutil.cpu_count() if PS_OK else 1
    ram_gb = round(psutil.virtual_memory().total / 1e9, 1) if PS_OK else 0
    disk_gb = round(psutil.disk_usage("/" if OS != "Windows" else "C:\\").total / 1e9, 1) if PS_OK else 0

    print(f"[CVIS] Agent starting")
    print(f"[CVIS] Device:  {device_name} ({device_id})")
    print(f"[CVIS] OS:      {OS} {platform.release()}")
    print(f"[CVIS] Type:    {detect_device_type()}")
    print(f"[CVIS] CPU:     {cpu_count} cores | RAM: {ram_gb}GB | Disk: {disk_gb}GB")
    print(f"[CVIS] Server:  {server}")
    print(f"[CVIS] psutil:  {'available' if PS_OK else 'missing - pip install psutil'}")
    print()

    fails = 0
    while True:
        try:
            m = collect_metrics()
            procs = collect_processes()
            payload = {
                "device_id": device_id, "device_name": device_name,
                "os": OS, "os_version": platform.release(),
                "hostname": socket.gethostname(),
                "arch": platform.machine(),
                "cpu_count": cpu_count, "ram_gb": ram_gb, "disk_gb": disk_gb,
                "device_type": detect_device_type(),
                "python": platform.python_version(),
                "timestamp": time.time(),
                "metrics": m, "processes": procs,
            }
            ok = push(server, args.key, device_id, device_name, payload)
            if ok:
                fails = 0
                print(f"[CVIS] ✓ {time.strftime('%H:%M:%S')} cpu={m['cpu_percent']}% mem={m['memory']}% health={m['health_score']}%")
            else:
                fails += 1
                if fails >= 3:
                    print(f"[CVIS] ✗ Server unreachable — retrying every {args.interval}s")
        except KeyboardInterrupt:
            print("\n[CVIS] Stopped.")
            break
        except Exception as e:
            print(f"[CVIS] Error: {e}")
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
