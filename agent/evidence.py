from dataclasses import dataclass
from enum import Enum
from typing import List
from datetime import datetime, timezone

from agent.domain import Domain
from agent.intent import Intent


class EvidenceStatus(Enum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


@dataclass
class EvidenceResult:
    status: EvidenceStatus
    missing: List[str]


EVIDENCE_REQUIREMENTS = {
    # ---- STATUS ----
    (Domain.SYSTEM_HEALTH, Intent.STATUS): ["posture"],
    (Domain.CPU, Intent.STATUS): ["cpu"],
    (Domain.MEMORY, Intent.STATUS): ["memory"],
    (Domain.STORAGE, Intent.STATUS): ["storage"],
    (Domain.THERMAL, Intent.STATUS): ["temperature"],

    # ---- EXPLANATION ----
    (Domain.CPU, Intent.EXPLAIN): ["cpu"],
    (Domain.MEMORY, Intent.EXPLAIN): ["memory"],
    (Domain.STORAGE, Intent.EXPLAIN): ["storage"],
    (Domain.THERMAL, Intent.EXPLAIN): ["temperature"],

    # ---- HISTORY / VISUAL ----
    (Domain.TRENDS, Intent.HISTORY): ["history"],
    (Domain.TRENDS, Intent.VISUALIZE): ["history"],
    (Domain.SYSTEM_HEALTH, Intent.VISUALIZE): ["history"],

    # ---- CAPABILITY ----
    (Domain.CAPABILITY, Intent.CAPABILITY): ["posture", "baseline"],

    # ---- BOTTLENECK ----
    (Domain.BOTTLENECK, Intent.STATUS): ["cpu", "memory"],
}


def is_fresh(facts: dict) -> bool:
    """
    Checks whether collected system facts are still valid.
    """
    try:
        meta = facts.get("metadata", {})
        collected_at = meta.get("collected_at")
        ttl = meta.get("ttl_seconds")

        if not collected_at or not ttl:
            return False

        collected = datetime.fromisoformat(collected_at.replace("Z", ""))
        if collected.tzinfo is None:
            collected = collected.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age = (now - collected).total_seconds()

        return age <= ttl

    except Exception:
        return False


def check_evidence(
    domains: List[Domain],
    intent: Intent,
    available_facts: dict
) -> EvidenceResult:
    required = set()

    for domain in domains:
        key = (domain, intent)
        if key in EVIDENCE_REQUIREMENTS:
            required.update(EVIDENCE_REQUIREMENTS[key])

    if not required:
        return EvidenceResult(
            status=EvidenceStatus.INSUFFICIENT,
            missing=["unspecified_evidence"]
        )

    if not is_fresh(available_facts):
        return EvidenceResult(
            status=EvidenceStatus.INSUFFICIENT,
            missing=["stale_data"]
        )

    missing = []
    for item in required:
        if item not in available_facts or available_facts[item] is None:
            missing.append(item)

    if not missing:
        return EvidenceResult(
            status=EvidenceStatus.SUFFICIENT,
            missing=[]
        )

    if len(missing) < len(required):
        return EvidenceResult(
            status=EvidenceStatus.PARTIAL,
            missing=missing
        )

    return EvidenceResult(
        status=EvidenceStatus.INSUFFICIENT,
        missing=missing
    )
