from fastapi import APIRouter
from backend.os_system.multi_agent_system import MultiAgentSystem

router = APIRouter()

# Initialize ONCE (shared instance)
os_system = MultiAgentSystem()


@router.get("/status")
def get_status():
    return os_system.get_system_status()
