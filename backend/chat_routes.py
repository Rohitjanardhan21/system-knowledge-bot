from fastapi import APIRouter
from pydantic import BaseModel
import os
import json
from openai import OpenAI

from backend.intelligence_pipeline import run_intelligence_pipeline
from backend.core.actions.action_executor import action_kill_high_cpu
from backend.memory_engine import MemoryEngine

router = APIRouter()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

memory = MemoryEngine()

# 🔥 Session-level pending decision (simple version)
pending_decision = {"data": None}


# ---------------- REQUEST ----------------
class ChatRequest(BaseModel):
    query: str


# ---------------- INTENT DETECTION ----------------
def detect_intent(query: str):
    q = query.lower()

    if q in ["yes", "do it", "execute now", "go ahead"]:
        return "confirm_yes"

    if q in ["no", "stop", "cancel"]:
        return "confirm_no"

    if any(x in q for x in ["fix", "resolve", "execute", "do it", "run"]):
        return "execute"

    if any(x in q for x in ["status", "health", "current state"]):
        return "status"

    if any(x in q for x in ["anomaly", "anomalies", "problem", "problems", "issue", "issues"]):
        return "anomaly"

    if any(x in q for x in ["predict", "prediction", "forecast", "future", "next"]):
        return "predict"

    if any(x in q for x in ["recommend", "recommendation", "suggestion", "what should", "what do you recommend"]):
        return "recommend"

    resource_phrases = [
        "what's causing",
        "whats causing",
        "what is causing",
        "what's using",
        "whats using",
        "what is using",
        "what is consuming",
        "what's consuming",
        "which app",
        "which application",
        "which process",
        "what process",
        "system slow",
        "too much cpu",
        "too much memory",
        "too much ram",
        "most cpu",
        "most memory",
        "most ram",
        "resources",
        "resource usage",
    ]

    if any(phrase in q for phrase in resource_phrases):
        return "resource_investigation"

    return "explain"


# ---------------- SAFE JSON ----------------
def safe_parse_json(text):
    try:
        return json.loads(text)
    except:
        return None


# ---------------- CHAT ROUTE ----------------
@router.post("/chat")
def chat_with_system(req: ChatRequest):

    query = req.query.strip().lower()

    state = run_intelligence_pipeline(allow_execution=False)

    decision = state.get("decision_data") or {}
    root = state.get("root_cause") or {}
    learning = state.get("learning") or {}
    recent_memory = memory.get_recent()

    intent = detect_intent(query)

    # =================================================
    # ✅ HANDLE CONFIRMATION (YES)
    # =================================================
    if intent == "confirm_yes":

        if not pending_decision["data"]:
            return {
                "mode": "info",
                "message": (
                    "There is no executable action pending. "
                    "The current recommendation is advisory and no system action was executed."
                ),
                "execution": "none",
            }

        decision_data = pending_decision["data"]
        pending_decision["data"] = None

        memory.store({
            "type": "action_confirmation",
            "decision": decision_data.get("decision"),
            "action": decision_data.get("action"),
            "result": "execution_deferred_to_operator_actions"
        })

        return {
            "mode": "info",
            "message": (
                "Confirmation received. Chat does not execute system actions directly. "
                "Review and run the recommended action from Operator Actions."
            ),
            "action": decision_data.get("action"),
            "execution": "deferred_to_operator_actions"
        }

    # =================================================
    # ❌ HANDLE CONFIRMATION (NO)
    # =================================================
    if intent == "confirm_no":
        pending_decision["data"] = None
        return {
            "mode": "cancelled",
            "message": "Action cancelled. Monitoring continues."
        }

    # =================================================
    # 🔥 EXECUTION REQUEST → ASK FIRST
    # =================================================
    if intent == "execute":

        if not decision.get("executable"):
            return {
                "mode": "info",
                "message": "No executable action available right now."
            }

        pending_decision["data"] = decision

        return {
            "mode": "confirm",
            "message": f"""
⚠ Issue Detected:
{decision.get('decision')}

🔥 Root Cause:
{root.get('explanation', 'Unknown')}

💡 Suggested Action:
{decision.get('action')}

Do you want me to execute this?
Reply with:
- yes
- no
- suggest alternative
"""
        }

    # =================================================
    # 📊 STATUS MODE
    # =================================================
    if intent == "status":
        return {
            "mode": "status",
            "cpu": state.get("cpu"),
            "memory": state.get("memory"),
            "disk": state.get("disk"),
            "decision": decision.get("decision"),
            "root_cause": root.get("explanation"),
            "patterns": learning.get("patterns", [])
        }

    # =================================================
    # 🚨 ANOMALY MODE
    # =================================================
    if intent == "anomaly":
        anomalies = learning.get("anomalies") or {}
        system_risk = state.get("system_risk")
        diagnosis = state.get("diagnosis") or {}

        if isinstance(diagnosis, dict):
            diagnosis_summary = (
                diagnosis.get("summary")
                or diagnosis.get("explanation")
                or diagnosis.get("cause")
            )
        else:
            diagnosis_summary = str(diagnosis) if diagnosis else None

        risk_text = (
            f"{float(system_risk) * 100:.0f}%"
            if isinstance(system_risk, (int, float))
            else "unavailable"
        )

        if diagnosis_summary:
            diagnosis_text = f"The main observed issue is: {diagnosis_summary}"
        else:
            diagnosis_text = "No specific primary diagnosis is currently available."

        anomaly_count = len(anomalies) if isinstance(anomalies, dict) else 0

        if anomaly_count:
            anomaly_text = f"{anomaly_count} anomaly group(s) are currently recorded."
        else:
            anomaly_text = "No additional anomaly groups are currently recorded."

        message = (
            f"The current system risk is {risk_text}.\n\n"
            f"{diagnosis_text}\n\n"
            f"{anomaly_text}"
        )

        return {
            "mode": "info",
            "message": message,
            "system_risk": system_risk,
            "anomalies": anomalies,
            "diagnosis": diagnosis,
        }

    # =================================================
    # 🔮 PREDICTION MODE
    # =================================================
    if intent == "predict":
        prediction = state.get("prediction")

        if isinstance(prediction, dict):
            prediction_type = prediction.get("type")
            prediction_confidence = prediction.get("confidence")

            if prediction_type:
                message = f"The current forecast classifies the expected system state as {prediction_type}."

                if isinstance(prediction_confidence, (int, float)):
                    message += (
                        f" Forecast confidence is "
                        f"{prediction_confidence * 100:.0f}%."
                    )
            else:
                message = (
                    "A forecast is available, but it does not currently "
                    "contain a named prediction class."
                )
        elif prediction is not None:
            message = f"The current forecast is: {prediction}"
        else:
            message = "No system forecast is currently available."

        return {
            "mode": "info",
            "message": message,
            "prediction": prediction,
        }

    # =================================================
    # 💡 RECOMMENDATION MODE
    # =================================================
    if intent == "recommend":
        action = decision.get("action")
        decision_text = decision.get("decision")
        explanation = (
            root.get("explanation")
            or root.get("summary")
            or root.get("cause")
            or root.get("primary_cause")
        )
        confidence = decision.get("confidence")
        executable = decision.get("executable")

        if action:
            message = f"The current recommended action is {action}."
        else:
            message = "The decision engine has not provided a specific action."

        if explanation:
            message += f" The identified cause is {explanation}."

        if isinstance(confidence, (int, float)):
            message += f" Decision confidence is {confidence * 100:.0f}%."

        if executable is True:
            message += (
                " The decision is marked executable, but chat will not "
                "execute it directly; use Operator Actions for execution."
            )
        else:
            message += (
                " This recommendation is advisory and is not currently "
                "marked for execution."
            )

        return {
            "mode": "info",
            "message": message,
            "decision": decision,
            "root_cause": root,
        }

    # =================================================
    # 🔎 RESOURCE INVESTIGATION MODE
    # =================================================
    if intent == "resource_investigation":
        diagnostic = action_kill_high_cpu()

        if not diagnostic.get("success"):
            return {
                "mode": "info",
                "message": (
                    "I couldn't inspect the running processes right now. "
                    "The diagnostic service reported an error."
                ),
                "diagnostic": diagnostic,
            }

        processes = diagnostic.get("processes") or []

        if not processes:
            return {
                "mode": "info",
                "message": "I couldn't find any process information to analyze.",
                "diagnostic": diagnostic,
            }

        top = processes[0]

        name = top.get("name") or "unknown process"
        pid = top.get("pid")
        cpu = top.get("cpu_percent")
        memory_pct = top.get("memory_percent")
        classification = top.get("classification") or "UNKNOWN"
        risk_level = top.get("risk_level") or "unknown"
        exe = top.get("exe")
        cmdline = top.get("cmdline")
        ppid = top.get("ppid")

        cpu_value = float(cpu or 0)
        memory_value = float(memory_pct or 0)

        message = (
            f"The main resource consumer is {name}. "
            f"It is currently using {cpu_value:.1f}% CPU "
            f"and {memory_value:.1f}% memory."
        )

        if pid is not None:
            message += f" PID: {pid}."

        if risk_level and risk_level != "unknown":
            message += f" Resource level: {risk_level}."

        if classification == "PROTECTED":
            message += (
                " This process is protected by the safety policy, "
                "so no termination was attempted."
            )
        elif classification == "SAFE_TO_REMEDIATE":
            message += (
                " It has been identified as a potential remediation candidate, "
                "but no action was taken automatically."
            )

        top_threads = top.get("top_threads") or []

        if top_threads:
            message += (
                f" Several threads inside this worker account for most of "
                f"its accumulated CPU activity."
            )

        message += (
            " The specific workload cannot currently be identified "
            "from process metadata. No process was terminated."
        )

        return {
            "mode": "info",
            "message": message,
            "processes": processes,
            "diagnostic": diagnostic,
        }

    # =================================================
    # 🧠 EXPLANATION MODE (LLM GROUNDED)
    # =================================================
    system_prompt = f"""
You are a SYSTEM INTELLIGENCE AGENT.

STRICT RULES:
- Use ONLY provided data
- NO assumptions
- Be precise and factual
- Explain like a senior systems engineer

Return JSON:

{{
 "summary": "...",
 "root_cause": "...",
 "explanation": "...",
 "recommended_action": "...",
 "confidence": 0.0
}}

DATA:
{json.dumps({
    "metrics": {
        "cpu": state.get("cpu"),
        "memory": state.get("memory"),
        "disk": state.get("disk")
    },
    "decision": decision,
    "root_cause": root,
    "learning": learning,
    "recent_memory": recent_memory[-5:]
}, indent=2)}
"""

    if client is None:
        return {
            "mode": "fallback",
            "response": (
                "LLM explanation service is not configured. "
                "Deterministic system status and intelligence data remain available."
            )
        }

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.query}
        ],
    )

    raw = response.choices[0].message.content
    parsed = safe_parse_json(raw)

    # fallback if not JSON
    if not parsed:
        return {
            "mode": "fallback",
            "response": raw
        }

    # 🔥 STORE MEMORY
    memory.store({
        "type": "explanation",
        "query": req.query,
        "summary": parsed.get("summary")
    })

    return {
        "mode": "explain",
        "structured": parsed
    }
