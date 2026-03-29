# ---------------------------------------------------------
# 🧠 CONTEXT-AWARE ENGINE (PRODUCTION GRADE)
# ---------------------------------------------------------

GAMING_KEYWORDS = ["game", "steam", "valorant", "csgo", "dota"]
DEV_KEYWORDS = ["code", "pycharm", "python", "node", "npm"]
BROWSER_KEYWORDS = ["chrome", "firefox", "edge"]

CRITICAL_PROCESSES = ["postgres", "nginx", "mysql", "docker"]

# 🔥 MEMORY (stability)
_last_context = "general"
_context_streak = 0


# ---------------------------------------------------------
# HELPER
# ---------------------------------------------------------
def match_keywords(name, keywords):
    return any(k in name for k in keywords)


# ---------------------------------------------------------
# CLASSIFY PROCESS
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
# MAIN CONTEXT DETECTION
# ---------------------------------------------------------
def detect_context(processes):

    global _last_context, _context_streak

    if not processes:
        return {
            "type": "idle",
            "confidence": 0.9,
            "reason": "No active processes"
        }

    # -----------------------------------------
    # 🔥 SORT TOP PROCESSES
    # -----------------------------------------
    processes = sorted(processes, key=lambda p: p.get("cpu", 0), reverse=True)
    top = processes[:5]

    scores = {
        "gaming": 0,
        "development": 0,
        "browsing": 0,
        "critical": 0
    }

    contributors = []

    total_cpu = sum(p.get("cpu", 0) for p in top) or 1

    # -----------------------------------------
    # 🔥 SCORING
    # -----------------------------------------
    for p in top:
        name = p.get("name")
        cpu = p.get("cpu", 0)

        category = classify(name)

        if category in scores:
            scores[category] += cpu

        contributors.append({
            "name": name,
            "cpu": cpu,
            "category": category,
            "weight": round(cpu / total_cpu, 2)
        })

    # -----------------------------------------
    # 🔥 CRITICAL OVERRIDE
    # -----------------------------------------
    if scores["critical"] > 15:
        return {
            "type": "critical",
            "confidence": 0.95,
            "reason": "Critical service dominating CPU",
            "contributors": contributors
        }

    # -----------------------------------------
    # 🔥 DOMINANT CONTEXT
    # -----------------------------------------
    dominant = max(scores, key=scores.get)
    dominant_score = scores[dominant]

    confidence = round(dominant_score / max(total_cpu, 1), 2)

    # -----------------------------------------
    # 🔥 LOW CONFIDENCE → MIXED
    # -----------------------------------------
    if confidence < 0.4:
        context_type = "mixed"
    elif dominant_score < 10:
        context_type = "general"
    else:
        context_type = dominant

    # -----------------------------------------
    # 🔥 STABILITY (ANTI-FLICKER)
    # -----------------------------------------
    if context_type == _last_context:
        _context_streak += 1
    else:
        _context_streak = 0

    if _context_streak < 2:
        context_type = _last_context

    _last_context = context_type

    # -----------------------------------------
    # 🔥 BUILD EXPLANATION
    # -----------------------------------------
    top_proc = contributors[0]

    reason = f"{top_proc['name']} driving {context_type} activity"

    return {
        "type": context_type,
        "confidence": confidence,
        "reason": reason,
        "contributors": contributors[:3]  # top 3 only
    }
