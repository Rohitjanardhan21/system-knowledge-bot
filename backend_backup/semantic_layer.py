"""
semantic_layer.py

Purpose:
--------
Convert raw system metrics into high-level semantic understanding.

This layer abstracts:
metrics → meaning

It enables:
- OS-agnostic reasoning
- domain-agnostic intelligence
- explainable AI outputs
"""

from typing import Dict, Any


# ─────────────────────────────────────────────
# CONFIG (can later be learned dynamically)
# ─────────────────────────────────────────────
CPU_THRESHOLDS = {
    "normal": 0.6,
    "elevated": 0.8,
}

MEMORY_THRESHOLDS = {
    "normal": 0.6,
    "elevated": 0.8,
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def normalize(value: float) -> float:
    """
    Normalize percentage (0–100) → (0–1)
    """
    if value > 1:
        return value / 100.0
    return value


def classify_load(value: float, thresholds: Dict[str, float]) -> Dict[str, str]:
    """
    Generic classification logic
    """
    if value >= thresholds["elevated"]:
        return {"state": "overloaded", "severity": "high"}
    elif value >= thresholds["normal"]:
        return {"state": "elevated", "severity": "medium"}
    else:
        return {"state": "normal", "severity": "low"}


# ─────────────────────────────────────────────
# CORE SEMANTIC INTERPRETATION
# ─────────────────────────────────────────────
def interpret(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main semantic interpretation function.

    Input:
        metrics = {
            "cpu": 75,
            "memory": 60,
            ...
        }

    Output:
        semantic = {
            "system_state": "stable",
            "compute": {...},
            "memory": {...},
            "overall_load": "...",
            "risk_level": "...",
            "summary": "..."
        }
    """

    # Normalize inputs
    cpu = normalize(metrics.get("cpu", 0))
    memory = normalize(metrics.get("memory", 0))

    # Classify individual components
    compute_state = classify_load(cpu, CPU_THRESHOLDS)
    memory_state = classify_load(memory, MEMORY_THRESHOLDS)

    # ─────────────────────────────────────────
    # AGGREGATE SYSTEM STATE
    # ─────────────────────────────────────────
    high_components = [
        c for c in [compute_state, memory_state]
        if c["severity"] == "high"
    ]

    medium_components = [
        c for c in [compute_state, memory_state]
        if c["severity"] == "medium"
    ]

    if high_components:
        system_state = "critical"
        risk_level = "high"
    elif len(medium_components) >= 1:
        system_state = "stressed"
        risk_level = "medium"
    else:
        system_state = "stable"
        risk_level = "low"

    # ─────────────────────────────────────────
    # OVERALL LOAD DESCRIPTION
    # ─────────────────────────────────────────
    avg_load = (cpu + memory) / 2

    if avg_load > 0.8:
        overall_load = "high"
    elif avg_load > 0.5:
        overall_load = "moderate"
    else:
        overall_load = "low"

    # ─────────────────────────────────────────
    # HUMAN-READABLE SUMMARY (VERY IMPORTANT)
    # ─────────────────────────────────────────
    summary = generate_summary(
        system_state,
        compute_state,
        memory_state,
        overall_load
    )

    # ─────────────────────────────────────────
    # FINAL STRUCTURED OUTPUT
    # ─────────────────────────────────────────
    return {
        "system_state": system_state,
        "risk_level": risk_level,
        "overall_load": overall_load,

        "compute": {
            "load": cpu,
            "state": compute_state["state"],
            "severity": compute_state["severity"],
        },

        "memory": {
            "pressure": memory,
            "state": memory_state["state"],
            "severity": memory_state["severity"],
        },

        "summary": summary
    }


# ─────────────────────────────────────────────
# NARRATIVE GENERATOR (KEY FOR UI + AI)
# ─────────────────────────────────────────────
def generate_summary(system_state, compute, memory, overall_load):
    """
    Generates human-readable explanation.
    This is what makes your system FEEL intelligent.
    """

    if system_state == "critical":
        return (
            f"System is under critical stress. "
            f"Compute is {compute['state']} and memory is {memory['state']}. "
            f"Immediate optimization is recommended."
        )

    elif system_state == "stressed":
        return (
            f"System load is elevated. "
            f"Compute is {compute['state']} with {overall_load} overall load. "
            f"Performance may degrade if sustained."
        )

    else:
        return (
            f"System is operating normally with {overall_load} load. "
            f"No immediate action required."
        )
