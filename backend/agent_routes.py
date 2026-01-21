from fastapi import APIRouter
from agent.agent_core import handle_question
import json

router = APIRouter(prefix="/agent")

FACTS_PATH = "system_facts/current.json"

def load_facts():
    try:
        with open(FACTS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

@router.post("/ask")
def ask_agent(payload: dict):
    question = payload.get("question", "")
    facts = load_facts()
    response = handle_question(question, facts)

    return {
        "mode": response.mode.value,
        "text": response.text,
        "visual": response.visual
    }
