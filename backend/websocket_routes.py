from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
import traceback
import time

from backend.system_routes import get_system_summary

router = APIRouter()

# ---------------------------------------------------------
# 🔥 CONNECTION MANAGER
# ---------------------------------------------------------

class ConnectionManager:

    def __init__(self):
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        print(f"✅ WS connected | clients={len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        print(f"🔌 WS disconnected | clients={len(self.active)}")

    async def broadcast(self, data: dict):
        dead = []

        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()

# ---------------------------------------------------------
# 🔥 GLOBAL STATE (SHARED LOOP)
# ---------------------------------------------------------

LAST_HASH = None
LAST_SENT = 0
GLOBAL_STATE = None


def has_changed(data: dict):
    global LAST_HASH

    try:
        # 🔥 REMOVE timestamp noise
        clean = {k: v for k, v in data.items() if k != "timestamp"}
        new_hash = hash(json.dumps(clean, sort_keys=True))
    except Exception:
        return True

    if new_hash != LAST_HASH:
        LAST_HASH = new_hash
        return True

    return False


def should_send():
    global LAST_SENT

    now = time.time()

    if now - LAST_SENT > 1:  # throttle
        LAST_SENT = now
        return True

    return False


# ---------------------------------------------------------
# 🔥 AGENT-AWARE EVENT DETECTOR
# ---------------------------------------------------------

def detect_event_type(data: dict):

    # 🔥 use agent reasoning instead of raw metrics
    agents = data.get("agents", {})

    decision = agents.get("decision", {}).get("output", {})
    action = decision.get("action")

    if data.get("risk", {}).get("level") == "CRITICAL":
        return "critical"

    if action and action != "do_nothing":
        return "decision"

    if data.get("anomalies"):
        return "anomaly"

    return "normal"


# ---------------------------------------------------------
# 🔥 BACKGROUND LOOP (CORE ENGINE)
# ---------------------------------------------------------

async def system_broadcast_loop():

    global GLOBAL_STATE

    while True:
        try:
            data = get_system_summary()
            GLOBAL_STATE = data

            if has_changed(data) and should_send():

                payload = {
                    "type": detect_event_type(data),
                    "data": data,
                    "timestamp": time.time()
                }

                await manager.broadcast(payload)

            # adaptive frequency
            if data.get("risk", {}).get("level") == "CRITICAL":
                await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(1.5)

        except Exception:
            print("❌ Broadcast loop error:")
            traceback.print_exc()
            await asyncio.sleep(2)


# ---------------------------------------------------------
# 🔥 START LOOP ON FIRST CONNECTION
# ---------------------------------------------------------

loop_started = False


async def ensure_loop():
    global loop_started
    if not loop_started:
        asyncio.create_task(system_broadcast_loop())
        loop_started = True


# ---------------------------------------------------------
# 🔥 MAIN WS
# ---------------------------------------------------------

@router.websocket("/ws/system")
async def system_ws(ws: WebSocket):

    await manager.connect(ws)
    await ensure_loop()

    try:
        # send latest state immediately
        if GLOBAL_STATE:
            await ws.send_json({
                "type": "init",
                "data": GLOBAL_STATE
            })

        while True:
            await asyncio.sleep(10)  # keep connection alive

    except WebSocketDisconnect:
        print("🔌 Client disconnected")

    finally:
        manager.disconnect(ws)


# ---------------------------------------------------------
# 🔥 HEALTH CHECK
# ---------------------------------------------------------

@router.websocket("/ws/health")
async def ws_health(ws: WebSocket):

    await ws.accept()

    try:
        while True:
            await ws.send_json({
                "status": "alive",
                "ts": time.time()
            })
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        print("🔌 Health WS disconnected")


# ---------------------------------------------------------
# 🚀 EXTERNAL BROADCAST
# ---------------------------------------------------------

async def broadcast_event(event: dict):
    await manager.broadcast(event)
