# ---------------------------------------------------------
# 🧠 COGNITIVE CONTEXT ENGINE (PRODUCTION / TOP 1%)
# ---------------------------------------------------------

from collections import deque
import math
import time

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

GAMING_KEYWORDS = ["game", "steam", "valorant", "csgo", "dota"]
DEV_KEYWORDS = ["code", "pycharm", "python", "node", "npm"]
BROWSER_KEYWORDS = ["chrome", "firefox", "edge"]

CRITICAL_PROCESSES = ["postgres", "nginx", "mysql", "docker"]

ABSTRACTION_MAP = {
    "gaming": "high_interactive_compute",
    "development": "productive_compute",
    "browsing": "light_interactive",
    "critical": "system_critical",
    "system": "background_compute",
    "mixed": "multi_modal_compute",
    "general": "general_compute",
    "unknown": "unclassified_compute"
}

# ---------------------------------------------------------
# MEMORY (TEMPORAL + LEARNING)
# ---------------------------------------------------------

_context_history = deque(maxlen=10)
_cpu_history = deque(maxlen=50)

_last_context = "general"
_context_streak = 0


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def match_keywords(name, keywords):
    return any(k in name for k in keywords)


def normalize_scores(scores):
    total = sum(scores.values()) or 1
    return {k: round(v / total, 3) for k, v in scores.items()}


def softmax(scores):
    exp_scores = {k: math.exp(v) for k, v in scores.items()}
    total = sum(exp_scores.values()) or 1
    return {k: round(v / total, 3) for k, v in exp_scores.items()}


# ---------------------------------------------------------
# CLASSIFIER
# ---------------------------------------------------------

def classify(name):
    name = (name or "").lower()

    if match_keywords(name, GAMING_KEYWORDS):
        return "gaming"

    if match_keywords(name, DEV_KEYWORDS):
        return "development"

    if match_keywords(name, BROWSER_KEYWORDS):
        return "browsing"

    if name in CRITICAL_PROCESSES:
        return "critical"

    return "system"


# ---------------------------------------------------------
# LEARNING BASELINE
# ---------------------------------------------------------

def update_baseline(cpu):
    _cpu_history.append(cpu)


def get_baseline():
    if not _cpu_history:
        return 40
    return sum(_cpu_history) / len(_cpu_history)


# ---------------------------------------------------------
# INTENT ENGINE
# ---------------------------------------------------------

def infer_intent(context_type, contributors):
    if context_type == "development":
        return "User actively writing or executing code"

    if context_type == "gaming":
        return "Real-time rendering / GPU-intensive workload"

    if context_type == "browsing":
        return "Interactive web usage"

    if context_type == "critical":
        return "System-critical service operation"

    if context_type == "mixed":
        return "Multiple concurrent workloads"

    return "Background or general system activity"


# ---------------------------------------------------------
# RISK ENGINE
# ---------------------------------------------------------

def assess_risk(context_type, cpu):
    baseline = get_baseline()

    if context_type == "critical" and cpu > 80:
        return "high"

    if cpu > baseline + 25:
        return "elevated"

    if cpu > baseline + 10:
        return "moderate"

    return "normal"


# ---------------------------------------------------------
# CONFIDENCE LABEL
# ---------------------------------------------------------

def confidence_label(conf):
    if conf < 0.5:
        return "low"
    elif conf < 0.75:
        return "moderate"
    return "high"


# ---------------------------------------------------------
# MAIN CONTEXT DETECTION
# ---------------------------------------------------------

def detect_context(processes):

    global _last_context, _context_streak

    if not processes:
        return {
            "type": "idle",
            "abstract_type": "idle_state",
            "confidence": 0.9,
            "confidence_level": "high",
            "reason": "No active processes detected",
            "intent": "System idle",
            "risk": "low",
            "contributors": []
        }

    # -----------------------------------------
    # SORT TOP PROCESSES
    # -----------------------------------------
    processes = sorted(processes, key=lambda p: p.get("cpu", 0), reverse=True)
    top = processes[:5]

    scores = {
        "gaming": 0,
        "development": 0,
        "browsing": 0,
        "critical": 0,
        "system": 0
    }

    contributors = []
    total_cpu = sum(p.get("cpu", 0) for p in top) or 1

    # -----------------------------------------
    # SCORING
    # -----------------------------------------
    for p in top:
        name = p.get("name", "")
        cpu = p.get("cpu", 0)

        category = classify(name)
        scores[category] += cpu

        contributors.append({
            "name": name,
            "cpu": cpu,
            "category": category,
            "weight": round(cpu / total_cpu, 3)
        })

    # -----------------------------------------
    # PROBABILITY DISTRIBUTION
    # -----------------------------------------
    probabilities = normalize_scores(scores)
    dominant = max(probabilities, key=probabilities.get)
    confidence = probabilities[dominant]

    # -----------------------------------------
    # UNKNOWN DETECTION
    # -----------------------------------------
    if max(scores.values()) < 5:
        context_type = "unknown"
    elif confidence < 0.4:
        context_type = "mixed"
    elif scores[dominant] < 10:
        context_type = "general"
    else:
        context_type = dominant

    # -----------------------------------------
    # TEMPORAL STABILITY (ANTI-FLICKER)
    # -----------------------------------------
    if context_type == _last_context:
        _context_streak += 1
    else:
        _context_streak = 0

    if _context_streak < 2:
        context_type = _last_context

    _last_context = context_type

    # -----------------------------------------
    # HISTORY SMOOTHING
    # -----------------------------------------
    _context_history.append(context_type)

    if len(_context_history) >= 5:
        context_type = max(set(_context_history), key=_context_history.count)

    # -----------------------------------------
    # BASELINE LEARNING
    # -----------------------------------------
    update_baseline(total_cpu)

    # -----------------------------------------
    # BUILD EXPLANATION
    # -----------------------------------------
    top_proc = contributors[0]

    reason = (
        f"{top_proc['name']} contributing "
        f"{round(top_proc['weight'] * 100)}% of load, "
        f"indicating {context_type} behavior"
    )

    # -----------------------------------------
    # FINAL OUTPUT
    # -----------------------------------------
    return {
        "type": context_type,
        "abstract_type": ABSTRACTION_MAP.get(context_type, "general_compute"),
        "confidence": round(confidence, 2),
        "confidence_level": confidence_label(confidence),
        "distribution": probabilities,
        "intent": infer_intent(context_type, contributors),
        "risk": assess_risk(context_type, total_cpu),
        "reason": reason,
        "contributors": contributors[:3],
        "timestamp": time.time()
    }
