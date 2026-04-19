from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from collections import defaultdict
import time

from backend.system_routes import summary

router = APIRouter()

# --------------------------------------------------
# 🧠 MEMORY STORE
# --------------------------------------------------

CHAT_MEMORY = defaultdict(list)

# --------------------------------------------------
# REQUEST MODEL
# --------------------------------------------------

class Query(BaseModel):
    query: str
    session_id: str = "default"

# --------------------------------------------------
# 🧠 INTENT CLASSIFIER
# --------------------------------------------------

def classify_intent(query: str):
    q = query.lower()

    if any(k in q for k in ["why", "cause"]):
        return "root_cause"
    if any(k in q for k in ["risk", "danger"]):
        return "risk"
    if any(k in q for k in ["predict", "future"]):
        return "prediction"
    if any(k in q for k in ["fix", "resolve", "solution"]):
        return "recommendation"
    if any(k in q for k in ["anomaly", "abnormal"]):
        return "anomaly"

    return "analysis"

# --------------------------------------------------
# 🧠 SEMANTIC LAYER
# --------------------------------------------------

def semantic_summary(data):
    cpu = data.get("cpu", 0)

    if cpu > 80:
        state = "high_load"
    elif cpu > 60:
        state = "moderate_load"
    else:
        state = "stable"

    return {
        "state": state,
        "cpu": cpu
    }

# --------------------------------------------------
# 🧠 CONTEXT ENGINE
# --------------------------------------------------

def build_context(history):
    last = history[-4:]
    return " → ".join([m["content"] for m in last if m["role"] == "user"])

# --------------------------------------------------
# 🧠 CONFIDENCE ENGINE
# --------------------------------------------------

def compute_confidence(data):
    base = 0.7

    if data.get("risk", {}).get("level") == "HIGH":
        base += 0.1

    if data.get("anomalies"):
        base += 0.1

    return round(min(base, 0.95), 2)

# --------------------------------------------------
# 🧠 TEMPORAL CONTEXT
# --------------------------------------------------

def temporal_context(data):
    return "Recent system behavior indicates a short-term fluctuation in load."

# --------------------------------------------------
# 🧠 SYSTEM FEED GENERATOR
# --------------------------------------------------

def generate_system_feed(data):
    return [
        f"CPU at {data.get('cpu')}%",
        f"Primary load from {data.get('root_cause', {}).get('process', 'unknown')}",
        f"Risk level {data.get('risk', {}).get('level', 'unknown')}"
    ]

# --------------------------------------------------
# 🧠 CORE REASONING ENGINE
# --------------------------------------------------

def generate_ai_response(data, query: str, history):

    intent = classify_intent(query)
    semantic = semantic_summary(data)
    context = build_context(history)
    confidence = compute_confidence(data)

    root = data.get("root_cause", {})
    risk = data.get("risk", {})
    prediction = data.get("prediction", {})
    anomalies = data.get("anomalies", [])
    recommendation = data.get("recommendation", {})

    process = root.get("process", "unknown")
    cpu = root.get("cpu", data.get("cpu", 0))

    # --------------------------------------------------
    # 🧠 BASE RESPONSE STRUCTURE
    # --------------------------------------------------

    cause = f"{process} is consuming {cpu}% CPU"
    effect = "This increases system load and may impact responsiveness"
    future = "If sustained, it may lead to performance degradation"
    action = recommendation.get("message", "No action required")

    why_now = temporal_context(data)

    context_block = f"\nContext: {context}\n" if context else ""

    # --------------------------------------------------
    # 🧠 INTENT-SPECIFIC RESPONSES
    # --------------------------------------------------

    if intent == "root_cause":
        response = f"""
CAUSE:
{cause}

EFFECT:
{effect}

WHY NOW:
{why_now}

RISK:
{risk.get("level", "unknown")}
{context_block}
"""

    elif intent == "risk":
        response = f"""
RISK LEVEL:
{risk.get("level", "unknown")}

CONTRIBUTORS:
- CPU: {data.get("cpu", 0)}%
- Memory: {data.get("memory", 0)}%
- Anomalies: {len(anomalies)}

EFFECT:
{effect}

{context_block}
"""

    elif intent == "prediction":
        response = f"""
FUTURE OUTLOOK:
{prediction.get("title", "unknown")}

DETAILS:
{prediction.get("details", "No details available")}

EXPECTED IMPACT:
{future}

{context_block}
"""

    elif intent == "anomaly":
        if not anomalies:
            response = "No anomalies detected. System is operating within expected bounds."
        else:
            details = "\n".join([
                f"- {a.get('metric')} spike (z={a.get('z_score')})"
                for a in anomalies
            ])
            response = f"""
ANOMALIES DETECTED:
{details}

IMPACT:
Potential instability or unexpected behavior

{context_block}
"""

    elif intent == "recommendation":
        response = f"""
RECOMMENDED ACTION:
{action}

EXPECTED OUTCOME:
Improved system stability and reduced load

CONFIDENCE:
{confidence}
"""

    else:
        response = f"""
SYSTEM STATE:
{semantic['state']}

CAUSE:
{cause}

EFFECT:
{effect}

FUTURE:
{future}

RECOMMENDATION:
{action}

CONFIDENCE:
{confidence}
{context_block}
"""

    # --------------------------------------------------
    # SAFETY NOTE
    # --------------------------------------------------

    response += (
        "\n⚠️ Validate critical actions before execution. "
        "Human supervision recommended."
    )

    return {
        "type": intent,
        "response": response.strip(),
        "confidence": confidence,
        "feed": generate_system_feed(data)
    }

# --------------------------------------------------
# 🔁 STREAMING ENGINE
# --------------------------------------------------

def stream_text(text: str):
    for chunk in text.split("\n"):
        yield chunk + "\n"
        time.sleep(0.05)

# --------------------------------------------------
# API: QUERY
# --------------------------------------------------

@router.post("/query")
def ai_query(q: Query):

    system_data = summary()
    history = CHAT_MEMORY[q.session_id]

    result = generate_ai_response(system_data, q.query, history)

    # STORE MEMORY
    history.append({"role": "user", "content": q.query})
    history.append({"role": "assistant", "content": result["response"]})

    CHAT_MEMORY[q.session_id] = history[-10:]

    return {
        "query": q.query,
        "answer": result["response"],
        "type": result["type"],
        "confidence": result["confidence"],
        "feed": result["feed"],
        "memory_size": len(CHAT_MEMORY[q.session_id])
    }

# --------------------------------------------------
# API: STREAM
# --------------------------------------------------

@router.post("/stream")
def ai_stream(q: Query):

    system_data = summary()
    history = CHAT_MEMORY[q.session_id]

    result = generate_ai_response(system_data, q.query, history)

    # STORE MEMORY
    history.append({"role": "user", "content": q.query})
    history.append({"role": "assistant", "content": result["response"]})

    CHAT_MEMORY[q.session_id] = history[-10:]

    return StreamingResponse(
        stream_text(result["response"]),
        media_type="text/plain"
    )
