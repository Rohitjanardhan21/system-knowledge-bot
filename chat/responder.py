import json

from chat.intent import detect_intent
from chat.data_resolver import (
    get_cpu,
    get_memory,
    get_storage,
    get_full_facts
)

from chat.health import evaluate_memory, evaluate_disk, overall_health
from chat.health_responses import summarize_health
from chat.slow_reasoner import analyze_slowness
from chat.slow_responses import explain_slowness
from chat.degradation import analyze_degradation
from chat.degradation_responses import explain_degradation
from chat.sre_policy import enforce_sre_policy

# Dimensions 1–7 engines
from chat.history_loader import load_recent_history
from chat.trend_metrics import memory_trend, disk_trend
from chat.baseline_metrics import memory_baseline, disk_baseline
from chat.severity_engine import classify_severity
from chat.prioritizer import prioritize
from chat.impact_engine import assess_impact
from chat.capability_engine import assess_capabilities
from chat.observer_engine import generate_observations
from chat.watch_state import enable_watch
from chat.decision_gate import should_speak


with open("knowledge/concepts.json") as f:
    KNOWLEDGE = json.load(f)


def answer(question: str) -> str:
    intent = detect_intent(question)
    q = question.lower()

    # ==================================================
    # SYSTEM HEALTH (SRE ENFORCED)
    # ==================================================
    if intent == "SYSTEM_STATUS":
        facts = get_full_facts()
        if not facts:
            return "System health cannot be evaluated right now."

        memory = facts.get("memory")
        storage = facts.get("storage")

        mem_status, mem_pct = evaluate_memory(memory)
        disk_status, disk_pct = evaluate_disk(storage)
        base = overall_health(mem_status, disk_status)

        summary = summarize_health(
            mem_status, mem_pct,
            disk_status, disk_pct,
            base
        )

        _, override = enforce_sre_policy(facts, base)
        return override if override else summary

    # ==================================================
    # BASELINE VS NORMAL (DIM 2 + DIM 7)
    # ==================================================
    if intent == "SYSTEM_BASELINE":
        history = load_recent_history()
        if len(history) < 5:
            return "I don’t have enough history yet to know what’s normal."

        mem_status, _ = memory_baseline(history)
        disk_status, _ = disk_baseline(history)

        severities = []
        if mem_status != "normal":
            severities.append("attention")
        if disk_status != "normal":
            severities.append("attention")

        speak = should_speak(
            severity_levels=severities,
            observations=[],
            intent=intent,
            freshness_ok=True
        )

        if not speak:
            return "Nothing stands out as unusual right now."

        msgs = []
        if mem_status != "normal":
            msgs.append("Available memory is outside its usual range.")
        if disk_status != "normal":
            msgs.append("Disk usage is outside its usual range.")

        return "Here’s how things compare to usual behavior:\n- " + "\n- ".join(msgs)

    # ==================================================
    # RAW FACTS
    # ==================================================
    if intent == "MEMORY_STATUS":
        mem = get_memory()
        return (
            f"Your system has {mem['total_mb']} MB RAM with "
            f"{mem['available_mb']} MB available."
            if mem else
            "Memory information is unavailable."
        )

    if intent == "CPU_INFO":
        cpu = get_cpu()
        return (
            f"Your system uses a {cpu['model']} with "
            f"{cpu['logical_cores']} logical cores."
            if cpu else
            "CPU information is unavailable."
        )

    if intent == "STORAGE_STATUS":
        storage = get_storage()
        if not storage:
            return "Storage information is unavailable."

        for fs in storage["filesystems"]:
            if fs["mount_point"] == "/":
                pct = (fs["used_gb"] / fs["size_gb"]) * 100
                return f"Main disk is {pct:.1f}% full."

    # ==================================================
    # HARDWARE DEGRADATION
    # ==================================================
    if intent == "DEGRADATION_CHECK":
        facts = get_full_facts()
        if not facts:
            return "Hardware health data is unavailable."

        disk_health = facts.get("disk_health", {})
        battery = facts.get("battery", {})

        result = explain_degradation(
            analyze_degradation(disk_health, battery)
        )

        notes = []
        if disk_health.get("status") == "unknown":
            notes.append("Disk SMART data is unavailable (expected in VMs).")
        if battery.get("status") == "not_applicable":
            notes.append("Battery health does not apply to this system.")

        if notes:
            result += "\n\nNotes:\n- " + "\n- ".join(notes)

        return result

    # ==================================================
    # DIMENSION 6 + 7: PROACTIVE (RESTRAINED)
    # ==================================================
    history = load_recent_history()
    if len(history) >= 5:
        mem_tr = memory_trend(history)
        disk_tr = disk_trend(history)
        mem_base, _ = memory_baseline(history)
        disk_base, _ = disk_baseline(history)

        mem_sev, _ = classify_severity(mem_tr[0], mem_tr[1], mem_base, "memory")
        disk_sev, _ = classify_severity(disk_tr[0], disk_tr[1], disk_base, "disk")

        observations = generate_observations(
            trends={"memory": mem_tr, "disk": disk_tr},
            baselines={"memory": mem_base, "disk": disk_base}
        )

        speak = should_speak(
            severity_levels=[mem_sev, disk_sev],
            observations=observations,
            intent=intent,
            freshness_ok=True
        )

        if speak and observations:
            return (
                "One thing I’ve noticed recently:\n- "
                + "\n- ".join(observations)
                + "\n\nIf you want, I can keep an eye on this for you."
            )

    # ==================================================
    # WATCH MODE
    # ==================================================
    if intent == "ENABLE_WATCH":
        if "memory" in q:
            enable_watch("memory")
            return "Okay, I’ll monitor memory behavior."
        if "disk" in q:
            enable_watch("disk")
            return "Okay, I’ll monitor disk usage."
        return "Tell me what you want me to monitor."

    # ==================================================
    # FALLBACK (REASSURANCE)
    # ==================================================
    return "Everything looks normal right now. Let me know if you want to explore something specific."
