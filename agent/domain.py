from enum import Enum
from dataclasses import dataclass
from typing import List


class Domain(Enum):
    SYSTEM_HEALTH = "system_health"
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    THERMAL = "thermal"          # ✅ ADDED
    BOTTLENECK = "bottleneck"
    CAPABILITY = "capability"
    TRENDS = "trends"
    EXPLANATION = "explanation"
    META = "meta"
    UNKNOWN = "unknown"


DOMAIN_KEYWORDS = {
    Domain.SYSTEM_HEALTH: {
        "healthy", "health", "status", "overall", "ok", "normal"
    },
    Domain.CPU: {
        "cpu", "processor", "compute", "core"
    },
    Domain.MEMORY: {
        "memory", "ram"
    },
    Domain.STORAGE: {
        "disk", "storage", "drive"
    },
    Domain.THERMAL: {
        "temperature", "thermal", "heat", "hot"
    },
    Domain.BOTTLENECK: {
        "bottleneck", "slow", "lag", "sluggish"
    },
    Domain.CAPABILITY: {
        "can", "handle", "run", "support"
    },
    Domain.TRENDS: {
        "trend", "today", "history", "over", "time"
    },
    Domain.EXPLANATION: {
        "why", "how", "explain"
    },
    Domain.META: {
        "you", "agent", "system", "this"
    },
}


@dataclass
class DomainResult:
    domains: List[Domain]
    allowed: bool


def resolve_domains(tokens: List[str]) -> DomainResult:
    matched = set()

    for token in tokens:
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if token in keywords:
                matched.add(domain)

    if not matched:
        return DomainResult(domains=[Domain.UNKNOWN], allowed=False)

    return DomainResult(domains=list(matched), allowed=True)
