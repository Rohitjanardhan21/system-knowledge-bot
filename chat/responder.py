import json

from chat.intent import detect_intent
from chat.data_resolver import (
    get_cpu,
    get_memory,
    get_storage,
    get_status,
    get_full_facts,
    get_history
)

from chat.health import (
    evaluate_memory,
    evaluate_disk,
    overall_health
)
from chat.health_responses import summarize_health

from chat.slow_reasoner import analyze_slowness
from chat.slow_responses import explain_slowness

from chat.degradation import analyze_degradation
from chat.degradation_responses import explain_degradation

from chat.change_detector import compare_memory, compare_disk
from chat.confidence import confidence
from chat.unknowns import report_unknowns
from chat.recommendations import recommend
from chat.capability import assess_capability


# -------------------------
# Load static knowledge
# -------------------------
with open("knowledge/concepts.json") as f:
    KNOWLEDGE = json.load(f)


def answer(question: str) -> str:
    """
    Main response function for the System Knowledge Bot.
    Combines real system facts, reasoning engines,
    and natural-language explanations.
    """

    intent = detect_intent(question)

    # --------------------------------------------------
    # CPU INFO
    # --------------------------------------------------
    if intent == "CPU_INFO":
        cpu = get_cpu()
        if cpu is None:
            return "I can’t access CPU information right now."

        return (
            f"Your system is running on a {cpu['model']} "
            f"with {cpu['logical_cores']} logical cores."
        )

    # --------------------------------------------------
    # MEMORY STATUS
    # --------------------------------------------------
    if intent == "MEMORY_STATUS":
        memory = get_memory()
        if memory is None:
            return "I can’t access memory information right now."

        return (
            f"Your system has {memory['total_mb']} MB of RAM, "
            f"with {memory['available_mb']} MB currently available."
        )

    # --------------------------------------------------
    # STORAGE STATUS
    # --------------------------------------------------
    if intent == "STORAGE_STATUS":
        storage = get_storage()
        if storage is None:
            return "I can’t access storage information right now."

        for fs in storage["filesystems"]:
            if fs["mount_point"] == "/":
                used_pct = (fs["used_gb"] / fs["size_gb"]) * 100
                return (
                    f"Your main disk is {used_pct:.1f}% full "
                    f"({fs['used_gb']} GB used out of {fs['size_gb']} GB)."
                )

        return "I couldn’t determine the usage of your main filesystem."

    # --------------------------------------------------
    # EXPLAIN CPU / RAM
    # --------------------------------------------------
    if intent == "EXPLAIN_CPU":
        return KNOWLEDGE["cpu"]["definition"]

    if intent == "EXPLAIN_RAM":
        return KNOWLEDGE["ram"]["definition"]

    # --------------------------------------------------
    # SYSTEM HEALTH (WITH CONFIDENCE + UNKNOWNs)
    # --------------------------------------------------
    if intent == "SYSTEM_STATUS":
        memory = get_memory()
        storage = get_storage()
        facts = get_full_facts()

        if memory is None or storage is None or facts is None:
            return (
                "I can’t evaluate system health right now because "
                "system data is unavailable."
            )

        mem_status, mem_pct = evaluate_memory(memory)
        disk_status, disk_pct = evaluate_disk(storage)
        overall = overall_health(mem_status, disk_status)

        response = summarize_health(
            mem_status, mem_pct,
            disk_status, disk_pct,
            overall
        )

        response += " " + confidence(
            "high" if overall == "healthy" else "medium"
        )

        unknowns = report_unknowns(facts)
        if unknowns:
            response += "\n\nWhat I can’t see:\n- " + "\n- ".join(unknowns)

        action = recommend(memory, storage)
        if action:
            response += "\n\nNext best action:\n- " + action

        return response

    # --------------------------------------------------
    # WHY IS SYSTEM SLOW?
    # --------------------------------------------------
    if intent == "SYSTEM_SLOW":
        memory = get_memory()
        storage = get_storage()

        if memory is None or storage is None:
            return (
                "I can’t analyze performance right now because "
                "system data is unavailable."
            )

        reasons, confidence_levels = analyze_slowness(memory, storage)
        response = explain_slowness(reasons, confidence_levels)
        response += "\n\n" + confidence(
            "high" if "high" in confidence_levels else "medium"
        )

        action = recommend(memory, storage)
        if action:
            response += "\n\nMost impactful improvement:\n- " + action

        return response

    # --------------------------------------------------
    # HARDWARE DEGRADATION
    # --------------------------------------------------
    if intent == "DEGRADATION_CHECK":
        facts = get_full_facts()

        if facts is None:
            return (
                "I can’t evaluate hardware health right now because "
                "system data is unavailable."
            )

        findings = analyze_degradation(
            facts.get("disk_health", {}),
            facts.get("battery", {})
        )

        response = explain_degradation(findings)

        unknowns = report_unknowns(facts)
        if unknowns:
            response += "\n\nWhat I can’t see:\n- " + "\n- ".join(unknowns)

        return response

    # --------------------------------------------------
    # WHAT CHANGED? (HISTORY-AWARE)
    # --------------------------------------------------
    if intent == "SYSTEM_CHANGE":
        history = get_history()
        if not history or len(history) < 2:
            return "I don’t have enough historical data to compare yet."

        prev, curr = history
        messages = []

        mem_change = compare_memory(prev["memory"], curr["memory"])
        if mem_change:
            messages.append(mem_change)

        prev_fs = prev["storage"]["filesystems"][0]
        curr_fs = curr["storage"]["filesystems"][0]
        disk_change = compare_disk(prev_fs, curr_fs)
        if disk_change:
            messages.append(disk_change)

        if not messages:
            return "No significant system changes detected recently."

        return (
            "Here’s what changed recently:\n- "
            + "\n- ".join(messages)
        )

    # --------------------------------------------------
    # CAPABILITY ASSESSMENT
    # --------------------------------------------------
    if intent == "CAPABILITY_CHECK":
        cpu = get_cpu()
        memory = get_memory()

        if cpu is None or memory is None:
            return "I can’t assess system capability right now."

        return assess_capability(cpu, memory)

    # --------------------------------------------------
    # UNKNOWN
    # --------------------------------------------------
    return (
        "I’m not sure how to help with that yet. "
        "You can ask about system health, performance issues, "
        "hardware degradation, changes over time, or system capability."
    )
