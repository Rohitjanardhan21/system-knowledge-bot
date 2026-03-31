from fastapi import APIRouter
from pydantic import BaseModel
import time
import uuid
import logging

from backend.self_healing_engine import SelfHealingEngine

router = APIRouter()
logger = logging.getLogger("ActionEngine")

self_healing_engine = SelfHealingEngine()

# ---------------------------------------------------------

# 🧠 IN-MEMORY STORE (can be replaced with DB later)

# ---------------------------------------------------------

PENDING_ACTIONS = {}
ACTION_HISTORY = {}

# ---------------------------------------------------------

# 📦 REQUEST MODELS

# ---------------------------------------------------------

class ActionRequest(BaseModel):
action: str
target: str | None = None
metadata: dict | None = None
confidence: float = 0.5
risk: str = "low"
source: str = "system"  # ai / system / user

# ---------------------------------------------------------

# 🔥 PROPOSE ACTION

# ---------------------------------------------------------

@router.post("/propose")
def propose_action(req: ActionRequest):

```
action_id = str(uuid.uuid4())

action_data = {
    "id": action_id,
    "action": req.action,
    "target": req.target,
    "metadata": req.metadata or {},
    "confidence": req.confidence,
    "risk": req.risk,
    "source": req.source,

    "status": "pending",
    "created_at": time.time(),
    "approved_at": None,
    "executed_at": None,
    "result": None
}

PENDING_ACTIONS[action_id] = action_data

logger.info(f"⚠️ Action proposed: {action_data}")

return {
    "status": "pending",
    "action_id": action_id,
    "message": "Action requires human approval before execution",
    "action": action_data
}
```

# ---------------------------------------------------------

# ✅ APPROVE ACTION

# ---------------------------------------------------------

@router.post("/approve/{action_id}")
def approve_action(action_id: str):

```
action = PENDING_ACTIONS.get(action_id)

if not action:
    return {"error": "Action not found"}

if action["status"] != "pending":
    return {"error": f"Action already {action['status']}"}

# mark approved
action["status"] = "approved"
action["approved_at"] = time.time()

logger.info(f"✅ Action approved: {action_id}")

# -----------------------------------------------------
# 🔥 SAFE EXECUTION
# -----------------------------------------------------
try:
    result = self_healing_engine.execute({
        "action": action["action"],
        "target": action["target"],
        "metadata": action["metadata"]
    })

    action["status"] = "executed"
    action["executed_at"] = time.time()
    action["result"] = result

    ACTION_HISTORY[action_id] = action
    del PENDING_ACTIONS[action_id]

    return {
        "status": "executed",
        "action_id": action_id,
        "result": result
    }

except Exception as e:

    action["status"] = "failed"
    action["result"] = str(e)

    ACTION_HISTORY[action_id] = action
    del PENDING_ACTIONS[action_id]

    logger.error(f"❌ Execution failed: {e}")

    return {
        "status": "failed",
        "error": str(e)
    }
```

# ---------------------------------------------------------

# ❌ REJECT ACTION

# ---------------------------------------------------------

@router.post("/reject/{action_id}")
def reject_action(action_id: str):

```
action = PENDING_ACTIONS.get(action_id)

if not action:
    return {"error": "Action not found"}

action["status"] = "rejected"
action["result"] = "Rejected by human"

ACTION_HISTORY[action_id] = action
del PENDING_ACTIONS[action_id]

logger.info(f"❌ Action rejected: {action_id}")

return {
    "status": "rejected",
    "action_id": action_id
}
```

# ---------------------------------------------------------

# 📋 GET ALL PENDING ACTIONS

# ---------------------------------------------------------

@router.get("/pending")
def get_pending_actions():
return {
"count": len(PENDING_ACTIONS),
"actions": list(PENDING_ACTIONS.values())
}

# ---------------------------------------------------------

# 📜 ACTION HISTORY

# ---------------------------------------------------------

@router.get("/history")
def get_action_history():
return {
"count": len(ACTION_HISTORY),
"actions": list(ACTION_HISTORY.values())
}

# ---------------------------------------------------------

# 🔍 GET SINGLE ACTION

# ---------------------------------------------------------

@router.get("/{action_id}")
def get_action(action_id: str):

```
if action_id in PENDING_ACTIONS:
    return PENDING_ACTIONS[action_id]

if action_id in ACTION_HISTORY:
    return ACTION_HISTORY[action_id]

return {"error": "Action not found"}
```
