import os
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
import sys
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


def get_credential_path():
    """Return the local path used to persist the device credential."""
    return os.path.join(os.path.expanduser("~"), ".cvis_credential")


def load_local_credential():
    """Load a previously enrolled device credential."""
    path = get_credential_path()

    try:
        with open(path, "r", encoding="utf-8") as f:
            credential = f.read().strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        print(f"[CVIS] Could not read local credential: {exc}")
        return None

    return credential or None


def save_local_credential(credential):
    """Persist the device credential with restrictive permissions."""
    path = get_credential_path()

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(credential)
            f.write("\n")
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise

    # Ensure permissions remain restrictive if the file already existed.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def enroll_device(server, enrollment_key, device_id, device_name):
    """
    Register this device and persist the returned device-bound credential.

    The enrollment credential is used only to call the administrative
    registration endpoint. The returned device credential is used for
    normal telemetry and command operations.
    """
    url = f"{server}/devices/register"

    payload = {
        "device_id": device_id,
        "device_name": device_name,
        "os": OS,
        "os_version": platform.release(),
        "hostname": socket.gethostname(),
        "capabilities": [
            "telemetry",
            "diagnostics",
            "remote_commands",
        ],
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": enrollment_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        credential = result.get("credential")

        if not credential:
            print("[CVIS] Enrollment failed: server returned no credential")
            return None

        save_local_credential(credential)

        print("[CVIS] Device enrolled successfully")
        print(f"[CVIS] Credential stored at: {get_credential_path()}")

        return credential

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[CVIS] Device enrollment failed: {e.code} {body}")
        return None

    except urllib.error.URLError as e:
        print(f"[CVIS] Device enrollment failed: {e.reason}")
        return None

    except Exception as e:
        print(f"[CVIS] Device enrollment error: {e}")
        return None


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


def transition_command(
    server,
    api_key,
    device_id,
    command_id,
    status,
    result=None,
):
    """Transition a remotely issued command through its lifecycle."""
    url = f"{server}/devices/{device_id}/commands/{command_id}/transition"
    data = json.dumps({
        "status": status,
        "result": result,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[CVIS] Command transition failed: {e.code} {body}")
        return None
    except Exception as e:
        print(f"[CVIS] Command transition error: {e}")
def execute_device_command(command_type, payload):
    """Execute an allowlisted command locally on the device."""
    payload = payload or {}

    # ------------------------------------------------------------
    # Diagnostic / read-only commands
    # ------------------------------------------------------------
    if command_type == "diagnostic.health_check":
        if PS_OK:
            cpu = psutil.cpu_percent(interval=0.2)
            mem = psutil.virtual_memory().percent
            return {
                "success": True,
                "command_type": command_type,
                "cpu_percent": round(cpu, 2),
                "memory_percent": round(mem, 2),
                "os": OS,
                "hostname": socket.gethostname(),
            }

        return {
            "success": True,
            "command_type": command_type,
            "os": OS,
            "hostname": socket.gethostname(),
            "message": "psutil unavailable; basic health check completed",
        }

    if command_type == "diagnostic.system_snapshot":
        result = {
            "success": True,
            "command_type": command_type,
            "os": OS,
            "os_version": platform.release(),
            "hostname": socket.gethostname(),
            "arch": platform.machine(),
            "python": platform.python_version(),
        }

        if PS_OK:
            result.update({
                "cpu_percent": round(psutil.cpu_percent(interval=0.2), 2),
                "memory_percent": round(
                    psutil.virtual_memory().percent, 2
                ),
                "cpu_count": psutil.cpu_count() or 1,
            })

            try:
                result["disk_percent"] = round(
                    psutil.disk_usage(
                        os.path.abspath(os.sep)
                    ).percent,
                    2,
                )
            except Exception:
                result["disk_percent"] = None

        return result

    if command_type == "diagnostic.process_list":
        if not PS_OK:
            return {
                "success": False,
                "error": "psutil is required for process listing",
                "command_type": command_type,
            }

        processes = collect_processes()

        return {
            "success": True,
            "command_type": command_type,
            "processes": processes,
        }

    # ------------------------------------------------------------
    # Safe remediation commands
    # ------------------------------------------------------------
    if command_type == "clear_temp":
        if OS == "Windows":
            import tempfile
            temp_dir = tempfile.gettempdir()
        else:
            temp_dir = "/tmp"

        if not os.path.isdir(temp_dir):
            return {
                "success": False,
                "error": f"Temporary directory not found: {temp_dir}",
                "command_type": command_type,
            }

        removed = 0
        failed = 0

        try:
            for name in os.listdir(temp_dir):
                path = os.path.join(temp_dir, name)

                # Never follow/remove the temp directory itself.
                try:
                    if os.path.isdir(path) and not os.path.islink(path):
                        import shutil
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    removed += 1
                except (PermissionError, FileNotFoundError, OSError):
                    failed += 1

            return {
                "success": failed == 0,
                "command_type": command_type,
                "action": "clear_temp",
                "directory": temp_dir,
                "removed": removed,
                "failed": failed,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "command_type": command_type,
            }

    if command_type == "clear_pip_cache":
        import subprocess

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "cache", "purge"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

            return {
                "success": proc.returncode == 0,
                "command_type": command_type,
                "action": "clear_pip_cache",
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-2000:],
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "command_type": command_type,
            }

    if command_type == "clear_docker_cache":
        import subprocess

        if OS != "Linux":
            return {
                "success": False,
                "error": "Docker cache cleanup currently supported on Linux only",
                "command_type": command_type,
            }

        try:
            proc = subprocess.run(
                ["docker", "system", "prune", "-f"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

            return {
                "success": proc.returncode == 0,
                "command_type": command_type,
                "action": "clear_docker_cache",
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-2000:],
            }

        except FileNotFoundError:
            return {
                "success": False,
                "error": "Docker executable not found",
                "command_type": command_type,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "command_type": command_type,
            }

    if command_type == "clear_logs":
        # Intentionally conservative: only clean known CVIS temporary
        # log files supplied explicitly by payload.
        paths = payload.get("paths", [])

        if not isinstance(paths, list):
            return {
                "success": False,
                "error": "paths must be a list",
                "command_type": command_type,
            }

        removed = 0
        failed = 0

        for raw_path in paths:
            if not isinstance(raw_path, str) or not raw_path:
                failed += 1
                continue

            try:
                path = os.path.abspath(raw_path)

                # Only allow files, never directories.
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
                else:
                    failed += 1
            except OSError:
                failed += 1

        return {
            "success": failed == 0,
            "command_type": command_type,
            "action": "clear_logs",
            "removed": removed,
            "failed": failed,
        }

    # ------------------------------------------------------------
    # Host-level remediation
    # ------------------------------------------------------------
    if command_type == "drop_caches":
        if OS != "Linux":
            return {
                "success": False,
                "error": "drop_caches is supported on Linux only",
                "command_type": command_type,
            }

        if not payload.get("confirm", False):
            return {
                "success": False,
                "error": "Dropping caches requires confirm=true",
                "command_type": command_type,
            }

        try:
            if os.geteuid() != 0:
                return {
                    "success": False,
                    "error": "drop_caches requires root privileges",
                    "command_type": command_type,
                }

            import subprocess

            proc = subprocess.run(
                ["sync"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            if proc.returncode != 0:
                return {
                    "success": False,
                    "error": "sync failed",
                    "command_type": command_type,
                    "stderr": proc.stderr[-2000:],
                }

            cache_level = str(payload.get("cache_level", "3"))

            if cache_level not in {"1", "2", "3"}:
                return {
                    "success": False,
                    "error": "cache_level must be 1, 2, or 3",
                    "command_type": command_type,
                }

            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write(cache_level)

            return {
                "success": True,
                "command_type": command_type,
                "action": "drop_caches",
                "cache_level": int(cache_level),
            }

        except PermissionError:
            return {
                "success": False,
                "error": "Permission denied writing drop_caches",
                "command_type": command_type,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "command_type": command_type,
            }

    # ------------------------------------------------------------
    # Process remediation
    # ------------------------------------------------------------
    if command_type == "kill_high_cpu":
        if not PS_OK:
            return {
                "success": False,
                "error": "psutil is required for process remediation",
                "command_type": command_type,
            }

        # Destructive process termination requires an exact identity.
        # PID alone is unsafe because operating systems reuse PIDs.
        pid = payload.get("pid")
        expected_create_time = payload.get("create_time")
        expected_name = payload.get("name")
        confirm = payload.get("confirm", False)

        if not confirm:
            return {
                "success": False,
                "error": "Process termination requires confirm=true",
                "command_type": command_type,
            }

        if pid is None or expected_create_time is None or not expected_name:
            return {
                "success": False,
                "error": (
                    "Exact process identity required: pid, create_time "
                    "and name must be supplied"
                ),
                "command_type": command_type,
                "pid": pid,
            }

        try:
            pid = int(pid)
            if pid <= 0:
                raise ValueError("PID must be positive")

            proc = psutil.Process(pid)

            # Critical process protection.
            if proc.pid == 1:
                return {
                    "success": False,
                    "error": "Refusing to terminate PID 1",
                    "command_type": command_type,
                    "pid": pid,
                }

            current_name = proc.name()

            # Never act on a process whose name changed.
            if current_name.lower() != str(expected_name).lower():
                return {
                    "success": False,
                    "error": "Process identity mismatch: name changed",
                    "command_type": command_type,
                    "pid": pid,
                    "expected_name": expected_name,
                    "actual_name": current_name,
                }

            current_create_time = proc.create_time()

            # Creation time is mandatory and must match tightly.
            try:
                if abs(
                    float(current_create_time)
                    - float(expected_create_time)
                ) > 0.01:
                    return {
                        "success": False,
                        "error": (
                            "Process identity mismatch: creation time changed"
                        ),
                        "command_type": command_type,
                        "pid": pid,
                        "expected_create_time": expected_create_time,
                        "actual_create_time": current_create_time,
                    }
            except (TypeError, ValueError):
                return {
                    "success": False,
                    "error": "Invalid expected process creation time",
                    "command_type": command_type,
                    "pid": pid,
                }

            # Re-read the process identity immediately before termination.
            verify = proc.as_dict(
                attrs=["pid", "name", "create_time", "username", "cmdline"]
            )

            if verify.get("pid") != pid:
                return {
                    "success": False,
                    "error": "Process identity mismatch: PID changed",
                    "command_type": command_type,
                    "pid": pid,
                }

            if (verify.get("name") or "").lower() != str(expected_name).lower():
                return {
                    "success": False,
                    "error": "Process identity mismatch during final validation",
                    "command_type": command_type,
                    "pid": pid,
                }

            verify_create_time = verify.get("create_time")

            if verify_create_time is None:
                return {
                    "success": False,
                    "error": "Process creation time unavailable",
                    "command_type": command_type,
                    "pid": pid,
                }

            if abs(
                float(verify_create_time)
                - float(expected_create_time)
            ) > 0.01:
                return {
                    "success": False,
                    "error": (
                        "Process identity mismatch during final "
                        "creation-time validation"
                    ),
                    "command_type": command_type,
                    "pid": pid,
                }

            # Never terminate the backend process itself.
            if pid == os.getpid():
                return {
                    "success": False,
                    "error": "Refusing to terminate current agent process",
                    "command_type": command_type,
                    "pid": pid,
                }

            # Re-check resource pressure immediately before acting.
            cpu = proc.cpu_percent(interval=1.0)
            mem = proc.memory_percent()

            if cpu < 60 and mem < 10:
                return {
                    "success": False,
                    "error": (
                        "Refusing to terminate process below the "
                        "resource-pressure threshold"
                    ),
                    "command_type": command_type,
                    "pid": pid,
                    "name": current_name,
                    "cpu_percent": round(cpu, 2),
                    "memory_percent": round(mem, 2),
                }

            before = {
                "pid": verify.get("pid"),
                "name": verify.get("name"),
                "create_time": verify.get("create_time"),
                "username": verify.get("username"),
                "cmdline": verify.get("cmdline"),
                "cpu_percent": round(cpu, 2),
                "memory_percent": round(mem, 2),
            }

            proc.terminate()

            try:
                proc.wait(timeout=5)
                terminated = True
            except psutil.TimeoutExpired:
                terminated = False

            return {
                "success": terminated,
                "action": "terminate",
                "command_type": command_type,
                "pid": pid,
                "name": current_name,
                "create_time": current_create_time,
                "cpu_percent": round(cpu, 2),
                "memory_percent": round(mem, 2),
                "terminated": terminated,
                "process": before,
                "message": (
                    "Process terminated successfully"
                    if terminated
                    else (
                        "Graceful termination timed out. "
                        "No force-kill was performed."
                    )
                ),
            }

        except psutil.NoSuchProcess:
            return {
                "success": False,
                "error": "Process no longer exists",
                "command_type": command_type,
                "pid": pid,
            }

        except psutil.AccessDenied:
            return {
                "success": False,
                "error": "Permission denied while terminating process",
                "command_type": command_type,
                "pid": pid,
            }

        except (TypeError, ValueError) as exc:
            return {
                "success": False,
                "error": str(exc),
                "command_type": command_type,
                "pid": pid,
            }

    return {
        "success": False,
        "error": f"Unsupported command type: {command_type}",
        "command_type": command_type,
    }
def poll_commands(server, api_key, device_id):
    """
    Poll the backend for pending commands.

    The backend owns durable command state. The agent only receives
    commands through the authenticated, device-bound API.
    """
    url = f"{server}/devices/{device_id}/commands/pending"

    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": api_key,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("commands", [])
    except urllib.error.HTTPError as e:
        print(f"[CVIS] Command poll failed: {e.code} {e.reason}")
        return []
    except Exception as e:
        print(f"[CVIS] Command poll error: {e}")
        return []


def process_pending_commands(server, api_key, device_id):
    """Claim and execute pending remote commands."""
    commands = poll_commands(server, api_key, device_id)

    for command in commands:
        command_id = command.get("command_id")
        command_type = command.get("command_type")
        payload = command.get("payload", {})

        if not command_id or not command_type:
            continue

        print(
            f"[CVIS] Command received: {command_type} "
            f"({command_id})"
        )

        executing = transition_command(
            server,
            api_key,
            device_id,
            command_id,
            "executing",
        )

        if not executing:
            print(
                f"[CVIS] Could not start command {command_id}"
            )
            continue

        result = execute_device_command(command_type, payload)

        final_status = "completed" if result.get("success") else "failed"

        print(
            f"[CVIS] DEBUG FINAL TRANSITION: "
            f"status={final_status} result={result!r}"
        )

        transition_command(
            server,
            api_key,
            device_id,
            command_id,
            final_status,
            result,
        )

        print(
            f"[CVIS] Command {command_id}: "
            f"{final_status} — {result}"
        )


def main():
    parser = argparse.ArgumentParser(description="CVIS Universal Agent")

    parser.add_argument(
        "--server",
        required=True,
        help="CVIS server URL e.g. http://192.168.1.10:8000",
    )

    parser.add_argument(
        "--key",
        default=None,
        help="Existing device credential (legacy/manual mode)",
    )

    parser.add_argument(
        "--enrollment-key",
        default=None,
        help="Administrative enrollment credential used only for first-time device enrollment",
    )

    parser.add_argument(
        "--device",
        default=None,
        help="Device name (default: hostname)",
    )

    parser.add_argument(
        "--interval",
        default=5,
        type=int,
        help="Push interval in seconds (default: 5)",
    )

    args = parser.parse_args()

    device_id   = get_device_id()
    device_name = args.device or socket.gethostname()
    server      = args.server.rstrip("/")

    # ------------------------------------------------------------
    # Credential selection
    #
    # Priority:
    #   1. Explicit --key (legacy/manual mode)
    #   2. Previously enrolled local device credential
    #   3. First-time enrollment using --enrollment-key
    #   4. Otherwise fail with a clear setup message
    #
    # The enrollment key is NEVER used for normal telemetry or
    # command operations.
    # ------------------------------------------------------------
    api_key = None

    if args.key:
        api_key = args.key
        print("[CVIS] Using explicitly supplied device credential")

    else:
        api_key = load_local_credential()

        if api_key:
            print("[CVIS] Using previously enrolled device credential")
            print(f"[CVIS] Credential source: {get_credential_path()}")

        elif args.enrollment_key:
            print("[CVIS] No local device credential found")
            print("[CVIS] Performing first-time device enrollment...")

            api_key = enroll_device(
                server,
                args.enrollment_key,
                device_id,
                device_name,
            )

            if not api_key:
                print("[CVIS] Enrollment failed; agent cannot start")
                return

        else:
            print("[CVIS] No device credential available")
            print(
                "[CVIS] First run: provide --enrollment-key, "
                "or provide an existing --key"
            )
            return

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
                server, api_key, device_id, device_name, payload
            )

            # Process any remotely issued commands after telemetry succeeds.
            if ok:
                process_pending_commands(
                    server,
                    api_key,
                    device_id,
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
