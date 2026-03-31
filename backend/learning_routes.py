from fastapi import APIRouter
from backend.learning_engine import LearningEngine

router = APIRouter()
engine = LearningEngine()

@router.post("/api/learn")
async def learn(payload: dict):

    action = payload.get("action")
    success = payload.get("success")

    engine.learn_from_feedback(action, success)

    return {"status": "updated"}
