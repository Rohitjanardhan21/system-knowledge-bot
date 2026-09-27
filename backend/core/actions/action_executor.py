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
        "label":       "Review High Resource Processes",
        "description": (
            "Identify CPU and memory consuming processes for "
            "user review before termination"
        ),
        "safe":        True,
        "targets":     ["CPU_STRESS", "THERMAL", "CRASH", "OOM", "MEMORY_EXHAUSTION"],
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
    import os
    import subprocess

    try:
        if os.name != "posix" or not os.path.exists("/proc/sys/vm/drop_caches"):
            return {
                "success": False,
                "details": ["Linux page-cache control is unavailable on this system."],
            }

        if os.geteuid() != 0:
            return {
                "success": False,
                "details": ["Dropping Linux page cache requires root privileges."],
            }

        # Ask the kernel to reclaim page cache, dentries and inodes.
        subprocess.run(
            ["sync"],
            check=True,
            timeout=10,
        )

        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("3\n")

        return {
            "success": True,
            "details": ["Linux page cache, dentries and inodes reclaimed."],
        }

    except Exception as e:
        return {"success": False, "details": [str(e)]}

def action_kill_high_cpu() -> dict:
    """
    Diagnose sustained CPU/memory pressure.

    This function is strictly diagnostic. It NEVER terminates processes.

    A process becomes a remediation candidate only when:
      * CPU usage is meaningfully elevated,
      * the process is not protected,
      * sufficient identity information is available,
      * and the observed state supports remediation.

    Destructive execution must independently revalidate the process identity.
    """
    try:
        import psutil
        import time
        import os

        SAMPLE_SECONDS = 1.0
        TOP_N = 5

        # ---------------------------------------------------------
        # HARD PROTECTION POLICY
        # ---------------------------------------------------------
        protected_names = {
            "system",
            "systemd",
            "init",
            "idle",
            "system idle process",
            "uvicorn",
        }

        current_pid = os.getpid()

        # ---------------------------------------------------------
        # DISCOVERY + CPU PRIME
        # ---------------------------------------------------------
        processes = []

        for proc in psutil.process_iter(
            [
                "pid",
                "ppid",
                "name",
                "memory_percent",
                "create_time",
                "username",
                "cmdline",
                "exe",
            ]
        ):
            try:
                proc.cpu_percent(None)
                processes.append(proc)

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess,
            ):
                continue
            except Exception:
                continue

        # ---------------------------------------------------------
        # SUSTAINED CPU SAMPLE
        # ---------------------------------------------------------
        time.sleep(SAMPLE_SECONDS)

        observed = []

        for proc in processes:
            try:
                info = proc.info

                pid = info.get("pid")
                name = info.get("name") or "unknown"
                normalized_name = name.lower()

                cpu = float(proc.cpu_percent(None) or 0.0)
                memory = float(info.get("memory_percent", 0.0) or 0.0)

                # -------------------------------------------------
                # THREAD-LEVEL CPU ATTRIBUTION
                # -------------------------------------------------
                top_threads = []
                try:
                    thread_rows = []
                    for thread in proc.threads():
                        cpu_time = float(thread.user_time + thread.system_time)
                        thread_rows.append(
                            {
                                "tid": thread.id,
                                "cpu_time_seconds": round(cpu_time, 2),
                            }
                        )

                    thread_rows.sort(
                        key=lambda item: item["cpu_time_seconds"],
                        reverse=True,
                    )
                    top_threads = thread_rows[:5]

                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    top_threads = []
                except Exception:
                    top_threads = []

                if cpu < 0:
                    cpu = 0.0

                if memory < 0:
                    memory = 0.0

                # -------------------------------------------------
                # HARD SAFETY CLASSIFICATION
                # -------------------------------------------------
                protection_reasons = []

                if pid == 1:
                    protection_reasons.append("pid_1")

                if pid == current_pid:
                    protection_reasons.append("current_backend_process")

                if normalized_name in protected_names:
                    protection_reasons.append("protected_process_name")

                username = info.get("username")

                # Processes without complete identity information
                # are never automatically considered safe to kill.
                identity_complete = (
                    pid is not None
                    and info.get("create_time") is not None
                    and bool(name)
                )

                if not identity_complete:
                    protection_reasons.append("incomplete_process_identity")

                # -------------------------------------------------
                # RESOURCE CLASSIFICATION
                # -------------------------------------------------
                if cpu >= 80 or memory >= 20:
                    risk_level = "high"
                elif cpu >= 60 or memory >= 10:
                    risk_level = "elevated"
                elif cpu >= 30 or memory >= 5:
                    risk_level = "moderate"
                else:
                    risk_level = "normal"

                resource_pressure = (
                    cpu >= 60
                    or memory >= 10
                )

                # -------------------------------------------------
                # CONFIDENCE
                # -------------------------------------------------
                confidence = 0
                confidence_reasons = []

                if cpu >= 80:
                    confidence += 50
                    confidence_reasons.append("high_cpu")
                elif cpu >= 60:
                    confidence += 35
                    confidence_reasons.append("elevated_cpu")
                elif cpu >= 30:
                    confidence += 15
                    confidence_reasons.append("moderate_cpu")

                if memory >= 20:
                    confidence += 25
                    confidence_reasons.append("high_memory")
                elif memory >= 10:
                    confidence += 15
                    confidence_reasons.append("elevated_memory")

                if identity_complete:
                    confidence += 15
                    confidence_reasons.append("complete_identity")

                if info.get("cmdline"):
                    confidence += 10
                    confidence_reasons.append("command_line_available")

                confidence = min(confidence, 100)

                # -------------------------------------------------
                # FINAL CLASSIFICATION
                # -------------------------------------------------
                if protection_reasons:
                    classification = "PROTECTED"

                elif not resource_pressure:
                    classification = "NOT_A_CANDIDATE"

                elif confidence >= 70:
                    classification = "SAFE_TO_REMEDIATE"

                else:
                    classification = "REVIEW_REQUIRED"

                observed.append(
                    {
                        "pid": pid,
                        "ppid": info.get("ppid"),
                        "name": name,
                        "cpu_percent": round(cpu, 2),
                        "memory_percent": round(memory, 2),
                        "top_threads": top_threads,
                        "create_time": info.get("create_time"),
                        "username": username,
                        "cmdline": info.get("cmdline"),
                        "exe": info.get("exe"),
                        "risk_level": risk_level,
                        "confidence": confidence,
                        "classification": classification,
                        "resource_pressure": resource_pressure,
                        "identity_complete": identity_complete,
                        "protection_reasons": protection_reasons,
                        "confidence_reasons": confidence_reasons,
                    }
                )

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess,
            ):
                continue
            except Exception:
                continue

        # ---------------------------------------------------------
        # RANKING
        # ---------------------------------------------------------
        observed.sort(
            key=lambda x: (
                x["cpu_percent"],
                x["memory_percent"],
                x["confidence"],
            ),
            reverse=True,
        )

        top = observed[:TOP_N]

        # Only SAFE_TO_REMEDIATE processes can become remediation
        # candidates. Protected and review-required processes never
        # cross this boundary automatically.
        remediation_candidates = [
            p for p in observed
            if p["classification"] == "SAFE_TO_REMEDIATE"
        ]

        primary = (
            remediation_candidates[0]
            if remediation_candidates
            else None
        )

        # ---------------------------------------------------------
        # RISK EXPLANATION
        # ---------------------------------------------------------
        if primary:
            risk = (
                f"REMEDIATION CANDIDATE: {primary['name']} "
                f"(PID {primary['pid']}) is using "
                f"{primary['cpu_percent']:.1f}% CPU and "
                f"{primary['memory_percent']:.1f}% memory. "
                f"Confidence {primary['confidence']}%. "
                "The process is eligible for review, but destructive "
                "execution must independently revalidate its identity."
            )

        elif observed:
            highest_pressure = observed[0]

            protected_count = sum(
                1 for p in observed
                if p["classification"] == "PROTECTED"
            )

            review_count = sum(
                1 for p in observed
                if p["classification"] == "REVIEW_REQUIRED"
            )

            risk = (
                "No automatically eligible remediation candidate found. "
                f"Highest observed process: {highest_pressure['name']} "
                f"(PID {highest_pressure['pid']}) at "
                f"{highest_pressure['cpu_percent']:.1f}% CPU and "
                f"{highest_pressure['memory_percent']:.1f}% memory. "
                f"Protected={protected_count}, "
                f"ReviewRequired={review_count}."
            )

        else:
            risk = "No process information was available."

        # ---------------------------------------------------------
        # HUMAN-READABLE DETAILS
        # ---------------------------------------------------------
        details = [
            (
                f"{p['name']} (PID {p['pid']}): "
                f"CPU {p['cpu_percent']:.1f}% "
                f"MEM {p['memory_percent']:.1f}% "
                f"RISK {p['risk_level'].upper()} "
                f"CLASS {p['classification']} "
                f"CONF {p['confidence']}%"
            )
            for p in top
        ]

        # ---------------------------------------------------------
        # RESULT
        # ---------------------------------------------------------
        return {
            "success": True,
            "sample_seconds": SAMPLE_SECONDS,
            "process_count": len(observed),
            "details": details,
            "processes": top,
            "risk": risk,
            "primary_process": primary,
            "remediation_candidate": primary is not None,
            "remediation_candidates": remediation_candidates,
            "policy": {
                "automatic_termination": False,
                "protected_pid_1": True,
                "protected_backend_pid": True,
                "identity_required": True,
                "creation_time_required": True,
                "review_required_for_uncertain_processes": True,
            },
            "note": (
                "Diagnostic only — no process was terminated. "
                "A remediation candidate is not permission to terminate. "
                "The destructive executor must independently revalidate "
                "PID, creation time, name, command line and safety policy "
                "immediately before execution."
            ),
        }

    except ImportError:
        return {
            "success": False,
            "details": ["psutil not installed"],
        }

    except Exception as exc:
        return {
            "success": False,
            "details": [f"diagnostic_failed: {exc}"],
        }

# ── Read-only diagnostic executors ─────────────────────────
def action_diagnostic_health_check() -> dict:
    """Return the current normalized health metrics."""
    from backend.core.system_adapter import get_metrics

    metrics = get_metrics()

    return {
        "success": True,
        "health_score": metrics.get("health_score"),
        "cpu_percent": metrics.get("cpu_percent"),
        "memory": metrics.get("memory"),
        "disk_percent": metrics.get("disk_percent"),
        "network_percent": metrics.get("network_percent"),
        "os": metrics.get("os"),
        "in_container": metrics.get("in_container"),
    }


def action_diagnostic_system_snapshot() -> dict:
    """Return current system metrics and the top processes."""
    from backend.core.system_adapter import get_metrics, get_processes

    metrics = get_metrics()
    processes = get_processes()

    processes.sort(
        key=lambda p: (
            float(p.get("cpu", 0) or 0),
            float(p.get("mem", 0) or 0),
        ),
        reverse=True,
    )

    return {
        "success": True,
        "metrics": metrics,
        "processes": processes[:20],
        "process_count": len(processes),
    }


def action_diagnostic_process_list() -> dict:
    """Return the top processes on the device."""
    from backend.core.system_adapter import get_processes

    processes = get_processes()

    processes.sort(
        key=lambda p: (
            float(p.get("cpu", 0) or 0),
            float(p.get("mem", 0) or 0),
        ),
        reverse=True,
    )

    return {
        "success": True,
        "processes": processes[:20],
        "process_count": len(processes),
    }


# ── Dispatcher ────────────────────────────────────────────
EXECUTORS = {
    "diagnostic.health_check":    action_diagnostic_health_check,
    "diagnostic.system_snapshot": action_diagnostic_system_snapshot,
    "diagnostic.process_list":    action_diagnostic_process_list,
    "clear_temp":                 action_clear_temp,
    "clear_docker_cache": action_clear_docker_cache,
    "clear_logs":         action_clear_logs,
    "clear_pip_cache":    action_clear_pip_cache,
    "drop_caches":        action_drop_caches,
    "kill_high_cpu":      action_kill_high_cpu,
}

# Actions permitted to run from autonomous remediation.
# Keep this list intentionally small and explicit.
AUTONOMOUS_ALLOWED_ACTIONS = {
    # No actions are currently approved for autonomous execution.
    # drop_caches requires host-level privileges unavailable to the backend container.
}


def execute_action(action_id: str, source: str = "manual") -> dict:
    if action_id not in EXECUTORS:
        return {"success": False, "error": f"Unknown action: {action_id}"}

    if source == "auto" and action_id not in AUTONOMOUS_ALLOWED_ACTIONS:
        log.warning("Blocked autonomous action: %s", action_id)
        return {
            "success": False,
            "blocked": True,
            "reason": "action_not_allowed_for_autonomous_execution",
            "action_id": action_id,
        }

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
