import re
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StrictStr

from backend.core.auth.auth import require_scope
from backend.core.learning_engine import (
    get_learning_engine,
    SUPPORTED_FEEDBACK_ACTIONS,
)
from backend.experience_store import consume_verified_experience

router = APIRouter()
engine = get_learning_engine()


class LearningFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: StrictStr
    experience_id: StrictStr


@router.get(
    "/api/learning/status",
    dependencies=[Depends(require_scope("read"))],
)
async def learning_status(
    principal: dict = Depends(require_scope("read")),
):
    workspace_id = principal.get("workspace_id") or "global"
    learner = (
        engine
        if workspace_id == "global"
        else get_learning_engine(workspace_id)
    )
    actions = {
        action: learner.get_action_stats(action)
        for action in sorted(SUPPORTED_FEEDBACK_ACTIONS)
    }
    return {
        "workspace_id": workspace_id,
        "actions": actions,
        "generated_at": time.time(),
    }


@router.post(
    "/api/learn",
    dependencies=[Depends(require_scope("write"))],
)
async def learn(
    payload: LearningFeedback,
    principal: dict = Depends(require_scope("write")),
):
    if payload.action not in SUPPORTED_FEEDBACK_ACTIONS:
        raise HTTPException(422, "Unsupported learning action")

    if re.fullmatch(r"[0-9a-f]{32}", payload.experience_id) is None:
        raise HTTPException(422, "Invalid experience_id")

    try:
        verification = consume_verified_experience(
            payload.experience_id,
            payload.action,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(
            503,
            "Verified experience evidence is unavailable",
        ) from exc

    if verification is None:
        raise HTTPException(
            409,
            "No unused verified successful experience matches this feedback",
        )

    try:
        learner = (
            engine
            if not principal.get("workspace_id")
            else get_learning_engine(principal["workspace_id"])
        )
        learner.learn_from_feedback(payload.action, verification)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    return {"status": "updated"}
