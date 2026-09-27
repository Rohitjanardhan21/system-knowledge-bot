"""
CVIS Process Intelligence
-------------------------
Enriches raw OS processes into user-facing application intelligence.

Responsibilities:
- Identify applications from process names/paths
- Classify applications
- Calculate resource impact
- Apply safe remediation policies
- Keep system-critical processes protected
"""

from __future__ import annotations

import os
from typing import Any, Dict


# ---------------------------------------------------------
# Application signatures
# ---------------------------------------------------------

APPLICATION_RULES = {
    # Browsers
    "chrome": {
        "application": "Google Chrome",
        "category": "browser",
        "kill_policy": "user_confirmation",
    },
    "google-chrome": {
        "application": "Google Chrome",
        "category": "browser",
        "kill_policy": "user_confirmation",
    },
    "firefox": {
        "application": "Mozilla Firefox",
        "category": "browser",
        "kill_policy": "user_confirmation",
    },
    "msedge": {
        "application": "Microsoft Edge",
        "category": "browser",
        "kill_policy": "user_confirmation",
    },

    # Development
    "code": {
        "application": "Visual Studio Code",
        "category": "developer_tool",
        "kill_policy": "user_confirmation",
    },
    "python": {
        "application": "Python",
        "category": "developer_tool",
        "kill_policy": "user_confirmation",
    },
    "java": {
        "application": "Java",
        "category": "developer_tool",
        "kill_policy": "user_confirmation",
    },

    # Containers / infrastructure
    "dockerd": {
        "application": "Docker",
        "category": "container_runtime",
        "kill_policy": "protected",
    },
    "containerd": {
        "application": "Container Runtime",
        "category": "container_runtime",
        "kill_policy": "protected",
    },
    "redis-server": {
        "application": "Redis",
        "category": "database",
        "kill_policy": "user_confirmation",
    },

    # Desktop/system
    "gnome-shell": {
        "application": "GNOME Shell",
        "category": "system",
        "kill_policy": "blocked",
    },
    "systemd": {
        "application": "systemd",
        "category": "system",
        "kill_policy": "blocked",
    },
    "systemd-journald": {
        "application": "systemd Journal",
        "category": "system",
        "kill_policy": "blocked",
    },

    # Gaming
    "steam": {
        "application": "Steam",
        "category": "game_platform",
        "kill_policy": "user_confirmation",
    },
    "steamwebhelper": {
        "application": "Steam",
        "category": "game_platform",
        "kill_policy": "user_confirmation",
    },
    "cs2": {
        "application": "Counter-Strike 2",
        "category": "game",
        "kill_policy": "user_confirmation",
    },
    "csgo": {
        "application": "Counter-Strike",
        "category": "game",
        "kill_policy": "user_confirmation",
    },
}


# Processes that should never be presented as ordinary
# "kill this process" candidates.
PROTECTED_NAMES = {
    "systemd",
    "systemd-journald",
    "init",
    "kthreadd",
    "kworker",
    "gnome-shell",
    "dbus-daemon",
}


# ---------------------------------------------------------
# Classification
# ---------------------------------------------------------

def _normalise_name(name: str | None) -> str:
    if not name:
        return "unknown"

    value = os.path.basename(str(name)).strip().lower()

    # Remove common executable suffixes.
    if value.endswith(".exe"):
        value = value[:-4]

    return value


def classify_process(
    name: str | None,
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
    pid: int | None = None,
    executable: str | None = None,
) -> Dict[str, Any]:
    """
    Convert a raw process into CVIS application intelligence.
    """

    normalised = _normalise_name(name)

    rule = APPLICATION_RULES.get(normalised)

    # Prefix matching handles variants such as:
    # chrome --type=renderer
    # python3
    if rule is None:
        for signature, candidate in APPLICATION_RULES.items():
            if normalised.startswith(signature):
                rule = candidate
                break

    if rule is None:
        application = name or "Unknown Process"
        category = "unknown"
        kill_policy = "user_confirmation"
    else:
        application = rule["application"]
        category = rule["category"]
        kill_policy = rule["kill_policy"]

    # Additional protection for kernel/system workers.
    if normalised.startswith("kworker"):
        application = "Linux Kernel Worker"
        category = "system"
        kill_policy = "blocked"

    if normalised in PROTECTED_NAMES:
        kill_policy = "blocked"

    cpu = float(cpu_percent or 0.0)
    memory = float(memory_percent or 0.0)

    impact = calculate_impact(cpu, memory)

    return {
        "pid": pid,
        "name": name or "unknown",
        "application": application,
        "category": category,
        "cpu_percent": round(cpu, 2),
        "memory_percent": round(memory, 2),
        "impact": impact,
        "kill_policy": kill_policy,
    }


# ---------------------------------------------------------
# Resource impact
# ---------------------------------------------------------

def calculate_impact(cpu_percent: float, memory_percent: float) -> str:
    """
    Determine user-facing resource impact.

    CPU and memory are deliberately evaluated independently,
    then the stronger signal wins.
    """

    cpu = float(cpu_percent or 0.0)
    memory = float(memory_percent or 0.0)

    if cpu >= 80 or memory >= 20:
        return "critical"

    if cpu >= 60 or memory >= 10:
        return "high"

    if cpu >= 30 or memory >= 5:
        return "moderate"

    return "low"


# ---------------------------------------------------------
# Ranking
# ---------------------------------------------------------

def enrich_processes(processes: list[dict]) -> list[dict]:
    """
    Enrich and rank a list of raw processes.

    Supports both telemetry formats currently used by CVIS:

        cpu_percent / memory_percent

    and:

        cpu / mem
    """

    enriched = []

    for process in processes or []:
        cpu = process.get(
            "cpu_percent",
            process.get("cpu", 0),
        )

        memory = process.get(
            "memory_percent",
            process.get("mem", 0),
        )

        item = classify_process(
            name=process.get("name"),
            cpu_percent=cpu,
            memory_percent=memory,
            pid=process.get("pid"),
            executable=process.get("exe"),
        )

        # Preserve useful original fields without replacing
        # the normalized intelligence fields.
        if process.get("exe"):
            item["executable"] = process["exe"]

        if process.get("cmdline"):
            item["cmdline"] = process["cmdline"]

        enriched.append(item)

    enriched.sort(
        key=lambda p: (
            float(p.get("cpu_percent", 0)),
            float(p.get("memory_percent", 0)),
        ),
        reverse=True,
    )

    return enriched


# ---------------------------------------------------------
# User-facing summary
# ---------------------------------------------------------

def build_resource_summary(
    processes: list[dict],
    system_memory_percent: float | None = None,
    system_cpu_percent: float | None = None,
) -> dict:
    """
    Produce a compact cognitive summary suitable for the
    notification layer or API.
    """

    enriched = enrich_processes(processes)

    significant = [
        p for p in enriched
        if p["impact"] in {"moderate", "high", "critical"}
    ]

    summary = {
        "processes": enriched,
        "significant_processes": significant[:10],
        "top_cpu": enriched[:5],
        "top_memory": sorted(
            enriched,
            key=lambda p: p["memory_percent"],
            reverse=True,
        )[:5],
        "system": {
            "cpu_percent": system_cpu_percent,
            "memory_percent": system_memory_percent,
        },
    }

    return summary


def build_user_message(process: dict) -> str:
    """
    Create a concise explanation for a desktop notification.
    """

    application = process["application"]
    category = process["category"]
    cpu = process["cpu_percent"]
    memory = process["memory_percent"]
    impact = process["impact"]

    return (
        f"{application} ({category}) is using "
        f"{cpu:.1f}% CPU and {memory:.1f}% memory. "
        f"Resource impact: {impact}."
    )
