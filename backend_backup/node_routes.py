from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter()

NODES_DIR = Path("system_facts/nodes")
NODES_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/node/update")
def update_node(data: dict):

    node_id = data.get("node", "unknown")

    file_path = NODES_DIR / f"{node_id}.json"
    file_path.write_text(json.dumps(data, indent=2))

    return {"status": "received"}
