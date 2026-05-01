"""
CVIS Action Executor
Turns warnings into one-click fixes.
When CVIS says "clear disk space" — this actually does it.
When CVIS says "restart process" — this actually does it.

Endpoints added to main.py:
    POST /actions/execute
    GET  /actions/available
"""
import os
import sys
import shutil
import subprocess
import platform
import logging
import time
from typing import Optional

log = logging.getLogger("cvis.actions")
OS  = platform.system()

# ── Action registry ───────────────────────────────────────
ACTIONS = {
    "clear_temp": {
        "id":          "clear_temp",
        "label":       "Clear Temp Files",
        "description": "Delete temporary files to free disk space",
        "safe":        True,
        "targets":     ["DISK_FULL", "DISK_IO_SATURATION"],
    },
    "clear_docker_cache": {
        "id":          "clear_docker_cache",
        "label":       "Clear Docker Cache",
        "description": "Remove unused Docker images and build cache",
        "safe":        True,
        "targets":     ["DISK_FULL"],
    },
    "clear_logs": {
        "id":          "clear_logs",
        "label":       "Rotate & Clear Logs",
        "description": "Vacuum system journal logs (keeps last 50MB)",
        "safe":        True,
        "targets":     ["DISK_FULL"],
    },
    "clear_pip_cache": {
        "id":          "clear_pip_cache",
        "label":       "Clear Pip Cache",
        "description": "Remove pip download cache",
        "safe":        True,
        "targets":     ["DISK_FULL"],
    },
    "drop_caches": {
        "id":          "drop_caches",
        "label":       "Drop Page Cache",
        "description": "Free OS memory page cache (Linux only)",
        "safe":        True,
        "targets":     ["OOM", "MEMORY_EXHAUSTION"],
    },
    "kill_high_cpu": {
        "id":          "kill_high_cpu",
        "label":       "Identify High CPU Process",
        "description": "Report top CPU consumer (does not kill automatically)",
        "safe":        True,
        "targets":     ["CPU_STRESS", "THERMAL", "CRASH"],
    },
}

# ── Executors ─────────────────────────────────────────────
def _run(cmd: str, shell=True) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True, timeout=30
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "Command timed out"
    except Exception as e:
        return -1, str(e)

def action_clear_temp() -> dict:
    freed = 0
    results = []

    # Linux/macOS
    tmp_paths = ["/tmp", "/var/tmp"] if OS != "Windows" else [os.environ.get("TEMP", "C:\\Temp")]
    for path in tmp_paths:
        if not os.path.exists(path):
            continue
        before = shutil.disk_usage(path).used
        try:
            for item in os.scandir(path):
                try:
                    if item.is_file():
                        os.unlink(item.path)
                    elif item.is_dir():
                        shutil.rmtree(item.path, ignore_errors=True)
                except Exception:
                    pass
            after = shutil.disk_usage(path).used
            freed += max(0, before - after)
            results.append(f"Cleaned {path}")
        except Exception as e:
            results.append(f"Could not clean {path}: {e}")

    return {
        "success": True,
        "freed_mb": round(freed / 1024 / 1024, 1),
        "details": results,
    }

def action_clear_docker_cache() -> dict:
    if not shutil.which("docker"):
        return {"success": False, "details": ["Docker not found"]}

    code, out = _run("docker system prune -f 2>&1")
    freed_line = [l for l in out.splitlines() if "reclaimed" in l.lower()]
    return {
        "success": code == 0,
        "freed_mb": 0,
        "details": [out[:300]],
        "freed_summary": freed_line[0] if freed_line else "Unknown amount reclaimed",
    }

def action_clear_logs() -> dict:
    results = []
    if OS == "Linux":
        code, out = _run("journalctl --vacuum-size=50M 2>&1")
        results.append(f"Journal: {out[:200]}")

    # Clear CVIS logs
    cvis_log_dirs = ["/app/logs", "./logs", os.path.expanduser("~/cvis/logs")]
    for d in cvis_log_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".log"):
                    try:
                        path = os.path.join(d, f)
                        size = os.path.getsize(path)
                        open(path, "w").close()
                        results.append(f"Cleared {f} ({size//1024}KB)")
                    except Exception:
                        pass

    return {"success": True, "details": results}

def action_clear_pip_cache() -> dict:
    code, out = _run("pip cache purge 2>&1")
    return {
        "success": code == 0,
        "details": [out[:200]],
    }

def action_drop_caches() -> dict:
    if OS != "Linux":
        return {"success": False, "details": ["Only supported on Linux"]}
    # This requires root — try with sudo
    code, out = _run("sync && echo 3 | sudo tee /proc/sys/vm/drop_caches 2>&1")
    return {
        "success": code == 0,
        "details": [out[:200] if out else "Page cache dropped"],
    }

def action_kill_high_cpu() -> dict:
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                pass
        procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
        top = procs[:5]
        details = [
            f"{p['name']} (PID {p['pid']}): CPU {p['cpu_percent']:.1f}% MEM {p['memory_percent']:.1f}%"
            for p in top
        ]
        return {
            "success": True,
            "details": details,
            "note": "Use 'kill -9 <PID>' to terminate a process if needed",
        }
    except ImportError:
        return {"success": False, "details": ["psutil not installed"]}

# ── Dispatcher ────────────────────────────────────────────
EXECUTORS = {
    "clear_temp":         action_clear_temp,
    "clear_docker_cache": action_clear_docker_cache,
    "clear_logs":         action_clear_logs,
    "clear_pip_cache":    action_clear_pip_cache,
    "drop_caches":        action_drop_caches,
    "kill_high_cpu":      action_kill_high_cpu,
}

def execute_action(action_id: str) -> dict:
    if action_id not in EXECUTORS:
        return {"success": False, "error": f"Unknown action: {action_id}"}
    start = time.time()
    try:
        result = EXECUTORS[action_id]()
        result["action_id"]    = action_id
        result["duration_ms"]  = round((time.time() - start) * 1000)
        result["timestamp"]    = time.time()
        log.info("Action executed: %s → success=%s", action_id, result.get("success"))
        return result
    except Exception as e:
        log.error("Action failed: %s → %s", action_id, e)
        return {"success": False, "error": str(e), "action_id": action_id}

def get_available_actions(failure_type: Optional[str] = None) -> list:
    actions = list(ACTIONS.values())
    if failure_type:
        actions = [a for a in actions if failure_type in a.get("targets", [])]
    return actions


# ── FastAPI routes to add to main.py ──────────────────────
"""
Add these routes to backend/main.py:

from backend.core.actions.action_executor import execute_action, get_available_actions

@app.get("/actions/available", tags=["Actions"])
async def list_actions(failure_type: str = None):
    return get_available_actions(failure_type)

@app.post("/actions/execute", tags=["Actions"])
async def run_action(action_id: str):
    return execute_action(action_id)
"""

if __name__ == "__main__":
    # Test all actions
    for action_id in EXECUTORS:
        print(f"\nTesting: {action_id}")
        result = execute_action(action_id)
        print(f"  Success: {result['success']}")
        for d in result.get("details", [])[:2]:
            print(f"  {d}")
