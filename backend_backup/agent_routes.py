from fastapi import APIRouter, HTTPException
from agent.agent_core import handle_question
import sys, os
sys.path.append(os.path.dirname(__file__))

from facts import load_facts

router = APIRouter(prefix="/agent")

@router.post("/ask")
def ask(payload: dict):
    question = payload.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="Missing question")

    facts = load_facts()
    return handle_question(question, facts)
