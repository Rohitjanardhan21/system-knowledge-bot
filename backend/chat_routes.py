from fastapi import APIRouter
from pydantic import BaseModel
import os
import json
from openai import OpenAI

from backend.intelligence_pipeline import run_intelligence_pipeline
from backend.action_executor import ActionExecutor
from backend.memory_engine import MemoryEngine

router = APIRouter()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

memory = MemoryEngine()

# 🔥 Session-level pending decision (simple version)
pending_decision = {"data": None}


# ---------------- REQUEST ----------------
class ChatRequest(BaseModel):
    query: str


# ---------------- INTENT DETECTION ----------------
def detect_intent(query: str):
    q = query.lower()

    if any(x in q for x in ["fix", "resolve", "execute", "do it", "run"]):
        return "execute"

    if any(x in q for x in ["status", "health", "current state"]):
        return "status"

    if q in ["yes", "do it", "execute now", "go ahead"]:
        return "confirm_yes"

    if q in ["no", "stop", "cancel"]:
        return "confirm_no"

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

    state = run_intelligence_pipeline()

    decision = state.get("decision_data", {})
    root = state.get("root_cause", {})
    learning = state.get("learning", {})
    recent_memory = memory.get_recent()

    intent = detect_intent(query)

    # =================================================
    # ✅ HANDLE CONFIRMATION (YES)
    # =================================================
    if intent == "confirm_yes":

        if not pending_decision["data"]:
            return {
                "mode": "info",
                "message": "No pending action to execute."
            }

        executor = ActionExecutor()
        result = executor.execute(pending_decision["data"])

        memory.store({
            "type": "action",
            "decision": pending_decision["data"].get("decision"),
            "action": pending_decision["data"].get("action"),
            "result": result.get("status")
        })

        pending_decision["data"] = None

        return {
            "mode": "executed",
            "message": "Action executed successfully",
            "result": result
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
