"""
CVIS Universal Agent — with Auto-Adaptation Layer
Runs on any OS, fingerprints the machine, learns its baseline,
and pushes adaptive metrics to CVIS server every 5 seconds.

Usage: python3 cvis_agent.py --server http://IP:8000 --key test123 --device mypc
"""
import argparse, platform, socket, time, uuid, json, urllib.request, urllib.error
import os, shutil, math, statistics

try:
    import psutil
    PS_OK = True
except ImportError:
    PS_OK = False

OS = platform.system()

# ── Device ID ─────────────────────────────────────────────
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

# ══════════════════════════════════════════════════════════
#  AUTO-ADAPTATION LAYER
#  Fingerprints the machine once, then learns its baseline
#  over 30 minutes to set intelligent, per-machine thresholds
# ══════════════════════════════════════════════════════════

class DeviceProfiler:
    """
    Runs once on startup. Collects hardware fingerprint in <100ms.
    No config needed — works on Linux, Windows, macOS automatically.
    """

    def __init__(self):
        self.profile = self._build()
        self.thresholds = self._calculate_thresholds()

    def _build(self) -> dict:
        uname = platform.uname()

        # ── CPU ──
        cpu_physical = psutil.cpu_count(logical=False) if PS_OK else 1
        cpu_logical  = psutil.cpu_count(logical=True)  if PS_OK else 1
        cpu_model    = platform.processor() or uname.machine

        # ── Memory ──
        ram_bytes = psutil.virtual_memory().total if PS_OK else 0
        ram_gb    = round(ram_bytes / 1e9, 1)

        # ── Disk ──
        disk_path = "C:\\" if OS == "Windows" else "/"
        try:
            disk_usage = psutil.disk_usage(disk_path)
            disk_gb    = round(disk_usage.total / 1e9, 1)
            disk_type  = self._detect_disk_type()
        except Exception:
            disk_gb   = 0
            disk_type = "unknown"

        # ── Battery — is it a laptop? ──
        is_laptop = False
        battery   = None
        try:
            b = psutil.sensors_battery()
            if b is not None:
                is_laptop = True
                battery   = {"percent": round(b.percent, 1), "charging": b.power_plugged}
        except Exception:
            pass

        # ── Virtualisation ──
        is_virtual = self._detect_virtual()
        vm_type    = self._detect_vm_type()

        # ── Docker ──
        has_docker = shutil.which("docker") is not None

        # ── GPU (basic check) ──
        has_gpu = self._detect_gpu()

        # ── Machine tier — used to pick threshold profile ──
        tier = self._classify_tier(ram_gb, cpu_physical)

        return {
            # Identity
            "hostname":       uname.node,
            "os":             OS,
            "os_version":     uname.version[:80],
            "os_release":     uname.release,
            "architecture":   uname.machine,
            # CPU
            "cpu_model":      cpu_model[:60],
            "cpu_cores":      cpu_physical,
            "cpu_threads":    cpu_logical,
            # Memory
            "ram_gb":         ram_gb,
            # Disk
            "disk_gb":        disk_gb,
            "disk_type":      disk_type,
            # Environment
            "python_version": platform.python_version(),
            "is_laptop":      is_laptop,
            "battery":        battery,
            "is_virtual":     is_virtual,
            "vm_type":        vm_type,
            "has_docker":     has_docker,
            "has_gpu":        has_gpu,
            # Classification
            "machine_tier":   tier,
            "profiled_at":    time.time(),
        }

    def _detect_disk_type(self) -> str:
        """Best-effort SSD vs HDD detection."""
        try:
            if OS == "Linux":
                # Check rotational flag in sysfs
                import glob
                for path in glob.glob("/sys/block/*/queue/rotational"):
                    with open(path) as f:
                        return "HDD" if f.read().strip() == "1" else "SSD"
            elif OS == "Windows":
                # Try WMI via subprocess
                import subprocess
                result = subprocess.run(
                    ["powershell", "-Command",
                     "Get-PhysicalDisk | Select-Object MediaType | ConvertTo-Json"],
                    capture_output=True, text=True, timeout=3
                )
                if "SSD" in result.stdout:
                    return "SSD"
                elif "HDD" in result.stdout:
                    return "HDD"
        except Exception:
            pass
        return "unknown"

    def _detect_virtual(self) -> bool:
        """Detect VirtualBox, VMware, WSL, Docker, KVM, QEMU."""
        # Docker env file
        if os.path.exists("/.dockerenv"):
            return True
        # Linux virtualisation markers
        if OS == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    cpuinfo = f.read().lower()
                    if any(x in cpuinfo for x in ["hypervisor", "vmware", "virtualbox", "kvm", "qemu"]):
                        return True
            except Exception:
                pass
            try:
                with open("/proc/version") as f:
                    if "microsoft" in f.read().lower():   # WSL
                        return True
            except Exception:
                pass
        # Platform string check
        version_str = platform.version().lower()
        vm_keywords = ["virtualbox", "vmware", "wsl", "hyperv", "hyper-v", "qemu", "xen"]
        return any(k in version_str for k in vm_keywords)

    def _detect_vm_type(self) -> str:
        """Return specific VM type string."""
        version_str = platform.version().lower()
        if os.path.exists("/.dockerenv"):       return "docker"
        if "microsoft" in version_str:           return "wsl"
        if "virtualbox" in version_str:          return "virtualbox"
        if "vmware" in version_str:              return "vmware"
        if "hyperv" in version_str or "hyper-v" in version_str: return "hyper-v"
        if "qemu" in version_str or "kvm" in version_str:       return "kvm"
        return "none"

    def _detect_gpu(self) -> bool:
        """Check if a discrete GPU is present."""
        try:
            if OS == "Linux":
                return os.path.exists("/dev/dri/card0")
            elif OS == "Windows":
                import subprocess
                result = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject Win32_VideoController).Name"],
                    capture_output=True, text=True, timeout=3
                )
                # Exclude basic display adapters
                output = result.stdout.strip()
                return bool(output) and "basic" not in output.lower()
        except Exception:
            pass
        return False

    def _classify_tier(self, ram_gb: float, cpu_cores: int) -> str:
        """
        Classify machine into a performance tier.
        Used to pick the right default threshold profile.
        """
        if ram_gb >= 32 and cpu_cores >= 8:   return "high-end"
        if ram_gb >= 16 and cpu_cores >= 4:   return "mid-range"
        if ram_gb >= 8  and cpu_cores >= 2:   return "standard"
        return "low-end"

    def _calculate_thresholds(self) -> dict:
        """
        Calculate adaptive thresholds based on hardware profile.
        A 32GB workstation and an 8GB laptop should NOT have
        the same OOM warning threshold.
        """
        p = self.profile
        ram   = p["ram_gb"]
        cores = p["cpu_cores"]
        disk  = p["disk_type"]
        vm    = p["is_virtual"]
        laptop= p["is_laptop"]

        # ── Memory thresholds ──
        # More RAM = more headroom before OOM is a real concern
        if ram >= 64:    mem_warn, mem_crit = 88, 95
        elif ram >= 32:  mem_warn, mem_crit = 85, 92
        elif ram >= 16:  mem_warn, mem_crit = 80, 90
        elif ram >= 8:   mem_warn, mem_crit = 75, 88
        else:            mem_warn, mem_crit = 65, 80   # low-end, warn early

        # ── CPU thresholds ──
        # More cores = more capacity before stress is a problem
        if cores >= 16:  cpu_warn, cpu_crit = 88, 95
        elif cores >= 8: cpu_warn, cpu_crit = 85, 92
        elif cores >= 4: cpu_warn, cpu_crit = 80, 90
        else:            cpu_warn, cpu_crit = 70, 85

        # ── Disk thresholds ──
        # SSD can handle higher utilisation than HDD
        if disk == "SSD":  disk_warn, disk_crit = 85, 95
        elif disk == "HDD": disk_warn, disk_crit = 75, 88
        else:               disk_warn, disk_crit = 80, 90

        # ── Virtual machine adjustments ──
        # VMs often show inflated metrics — loosen thresholds to reduce noise
        if vm:
            mem_warn  = min(mem_warn + 5, 95)
            cpu_warn  = min(cpu_warn + 5, 95)
            disk_warn = min(disk_warn + 5, 95)

        # ── Laptop adjustments ──
        # Laptops throttle harder — warn earlier
        if laptop:
            cpu_warn  = max(cpu_warn - 5, 60)
            cpu_crit  = max(cpu_crit - 5, 75)
            mem_warn  = max(mem_warn - 3, 60)

        return {
            "mem_warn":   mem_warn,
            "mem_crit":   mem_crit,
            "cpu_warn":   cpu_warn,
            "cpu_crit":   cpu_crit,
            "disk_warn":  disk_warn,
            "disk_crit":  disk_crit,
            "source":     "hardware-profile",  # will change to "baseline" after learning
        }

    def print_summary(self):
        p = self.profile
        t = self.thresholds
        print(f"[CVIS] ── Auto-Adaptation Layer ──────────────────")
        print(f"[CVIS] Tier:     {p['machine_tier']} ({p['ram_gb']}GB RAM, {p['cpu_cores']} cores)")
        print(f"[CVIS] Disk:     {p['disk_type']} · Virtual: {p['is_virtual']} ({p['vm_type']})")
        print(f"[CVIS] Laptop:   {p['is_laptop']} · GPU: {p['has_gpu']}")
        print(f"[CVIS] Thresholds (auto-calculated):")
        print(f"[CVIS]   CPU  warn={t['cpu_warn']}%  crit={t['cpu_crit']}%")
        print(f"[CVIS]   MEM  warn={t['mem_warn']}%  crit={t['mem_crit']}%")
        print(f"[CVIS]   DISK warn={t['disk_warn']}%  crit={t['disk_crit']}%")
        print(f"[CVIS] ─────────────────────────────────────────────")


class BaselineLearner:
    """
    Watches the machine for BASELINE_WINDOW seconds.
    Learns what "normal" looks like for THIS specific machine.
    After learning, tightens thresholds around the real baseline
    to eliminate false alarms.

    Example: if your machine always idles at 65% CPU,
    CVIS stops treating 65% as elevated.
    """

    BASELINE_WINDOW = 1800   # 30 minutes in seconds
    MIN_SAMPLES     = 30     # minimum samples before baseline is trusted
    STDDEV_MULT     = 2.5    # warn at mean + 2.5 * stddev

    def __init__(self, profiler: DeviceProfiler):
        self.profiler   = profiler
        self.samples    = {"cpu": [], "mem": [], "disk": [], "net": []}
        self.start_time = time.time()
        self.learned    = False
        self.baseline   = {}

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def progress_pct(self) -> int:
        return min(100, int(self.elapsed / self.BASELINE_WINDOW * 100))

    def add_sample(self, metrics: dict):
        """Feed a metrics snapshot into the learner."""
        if self.learned:
            return
        self.samples["cpu"].append(metrics.get("cpu_percent", 0))
        self.samples["mem"].append(metrics.get("memory", 0))
        self.samples["disk"].append(metrics.get("disk_percent", 0))
        self.samples["net"].append(metrics.get("network_percent", 0))

        # Check if we have enough data to learn
        n = len(self.samples["cpu"])
        if n >= self.MIN_SAMPLES and self.elapsed >= self.BASELINE_WINDOW:
            self._finalise()

    def _finalise(self):
        """Calculate baseline and update thresholds."""
        self.baseline = {}
        new_thresholds = dict(self.profiler.thresholds)

        for metric, values in self.samples.items():
            if not values:
                continue
            mean   = statistics.mean(values)
            stddev = statistics.stdev(values) if len(values) > 1 else 5.0
            p95    = sorted(values)[int(len(values) * 0.95)]

            self.baseline[metric] = {
                "mean":   round(mean, 2),
                "stddev": round(stddev, 2),
                "p95":    round(p95, 2),
                "min":    round(min(values), 2),
                "max":    round(max(values), 2),
                "samples": len(values),
            }

            # Calculate learned threshold:
            # warn at p95 + 1 stddev, crit at p95 + 2 stddevs
            # but never lower than hardware-profile thresholds
            learned_warn = round(p95 + stddev, 1)
            learned_crit = round(p95 + stddev * 2, 1)

            if metric == "cpu":
                new_thresholds["cpu_warn"] = max(
                    min(learned_warn, 95),
                    self.profiler.thresholds["cpu_warn"]
                )
                new_thresholds["cpu_crit"] = max(
                    min(learned_crit, 98),
                    self.profiler.thresholds["cpu_crit"]
                )
            elif metric == "mem":
                new_thresholds["mem_warn"] = max(
                    min(learned_warn, 95),
                    self.profiler.thresholds["mem_warn"]
                )
                new_thresholds["mem_crit"] = max(
                    min(learned_crit, 98),
                    self.profiler.thresholds["mem_crit"]
                )
            elif metric == "disk":
                new_thresholds["disk_warn"] = max(
                    min(learned_warn, 95),
                    self.profiler.thresholds["disk_warn"]
                )
                new_thresholds["disk_crit"] = max(
                    min(learned_crit, 98),
                    self.profiler.thresholds["disk_crit"]
                )

        new_thresholds["source"]      = "baseline-learned"
        new_thresholds["learned_at"]  = time.time()
        new_thresholds["sample_count"] = len(self.samples["cpu"])

        self.profiler.thresholds = new_thresholds
        self.learned = True

        print(f"\n[CVIS] ── Baseline Learned ───────────────────────")
        for metric, b in self.baseline.items():
            print(f"[CVIS]   {metric:4s}  mean={b['mean']}%  p95={b['p95']}%  stddev={b['stddev']}")
        print(f"[CVIS] Updated thresholds (learned from your machine):")
        t = self.profiler.thresholds
        print(f"[CVIS]   CPU  warn={t['cpu_warn']}%  crit={t['cpu_crit']}%")
        print(f"[CVIS]   MEM  warn={t['mem_warn']}%  crit={t['mem_crit']}%")
        print(f"[CVIS]   DISK warn={t['disk_warn']}%  crit={t['disk_crit']}%")
        print(f"[CVIS] ─────────────────────────────────────────────\n")

    def status_line(self) -> str:
        if self.learned:
            return "baseline-learned"
        n = len(self.samples["cpu"])
        return f"learning ({self.progress_pct}% — {n} samples)"


# ══════════════════════════════════════════════════════════
#  ORIGINAL AGENT CODE (unchanged, adaptation injected below)
# ══════════════════════════════════════════════════════════

def collect_metrics():
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
    if OS == "Darwin":  return "mac"
    if shutil.which("docker"): return "docker-host"
    if PS_OK and (psutil.cpu_count() or 1) <= 2 and psutil.virtual_memory().total < 4e9:
        return "embedded-linux"
    return "linux-server"

def push(server, key, device_id, name, payload):
    url  = f"{server}/devices/{device_id}/metrics"
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data,
           headers={"Content-Type":"application/json","X-API-Key":key,
                    "X-Device-Name":name}, method="POST")
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
    parser.add_argument("--server",   required=True)
    parser.add_argument("--key",      required=True)
    parser.add_argument("--device",   default=None)
    parser.add_argument("--interval", default=5, type=int)
    parser.add_argument("--no-adapt", action="store_true",
                        help="Disable auto-adaptation layer")
    args = parser.parse_args()

    device_id   = get_device_id()
    device_name = args.device or socket.gethostname()
    server      = args.server.rstrip("/")

    cpu_count = psutil.cpu_count() if PS_OK else 1
    ram_gb    = round(psutil.virtual_memory().total / 1e9, 1) if PS_OK else 0
    disk_gb   = round(psutil.disk_usage("/" if OS != "Windows" else "C:\\").total / 1e9, 1) if PS_OK else 0

    print(f"[CVIS] Agent starting")
    print(f"[CVIS] Device:  {device_name} ({device_id})")
    print(f"[CVIS] OS:      {OS} {platform.release()}")
    print(f"[CVIS] Type:    {detect_device_type()}")
    print(f"[CVIS] CPU:     {cpu_count} cores | RAM: {ram_gb}GB | Disk: {disk_gb}GB")
    print(f"[CVIS] Server:  {server}")
    print(f"[CVIS] psutil:  {'available' if PS_OK else 'missing — pip install psutil'}")
    print()

    # ── Auto-Adaptation Layer ──
    profiler = None
    learner  = None

    if not args.no_adapt and PS_OK:
        print("[CVIS] Running device profiler...")
        profiler = DeviceProfiler()
        profiler.print_summary()
        learner  = BaselineLearner(profiler)
        print(f"[CVIS] Baseline learning starts now — will complete in 30 min")
        print(f"[CVIS] Thresholds will auto-update once baseline is established")
        print()

    fails = 0
    while True:
        try:
            m     = collect_metrics()
            procs = collect_processes()

            # Feed sample into baseline learner
            if learner:
                learner.add_sample(m)

            # Build adaptive info to send to server
            adapt_info = {}
            if profiler:
                adapt_info = {
                    "device_profile":  profiler.profile,
                    "thresholds":      profiler.thresholds,
                    "baseline_status": learner.status_line() if learner else "disabled",
                    "baseline":        learner.baseline     if learner else {},
                }

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
                "device_type": detect_device_type(),
                "python":      platform.python_version(),
                "timestamp":   time.time(),
                "metrics":     m,
                "processes":   procs,
                "adaptation":  adapt_info,   # ← new field
            }

            ok = push(server, args.key, device_id, device_name, payload)
            if ok:
                fails = 0
                adapt_str = ""
                if learner:
                    adapt_str = f" [{learner.status_line()}]"
                print(f"[CVIS] ✓ {time.strftime('%H:%M:%S')} "
                      f"cpu={m['cpu_percent']}% "
                      f"mem={m['memory']}% "
                      f"health={m['health_score']}%"
                      f"{adapt_str}")
            else:
                fails += 1
                if fails >= 3:
                    print(f"[CVIS] ✗ Server unreachable — retrying every {args.interval}s")

        except KeyboardInterrupt:
            print("\n[CVIS] Stopped.")
            if learner and learner.baseline:
                print("[CVIS] Final baseline summary:")
                for metric, b in learner.baseline.items():
                    print(f"[CVIS]   {metric}: mean={b['mean']}% p95={b['p95']}%")
            break
        except Exception as e:
            print(f"[CVIS] Error: {e}")

        time.sleep(args.interval)

if __name__ == "__main__":
    main()
