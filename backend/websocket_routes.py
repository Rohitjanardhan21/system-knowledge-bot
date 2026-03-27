from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
from backend.system_routes import get_system_summary

router = APIRouter()


@router.websocket("/ws/system")
async def system_ws(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket connected")

    try:
        while True:
            try:
                data = get_system_summary()
                await websocket.send_json(data)
                await asyncio.sleep(1)

            except WebSocketDisconnect:
                print("🔌 Client disconnected")
                break

            except Exception as e:
                import traceback
                print("❌ WS internal error:")
                traceback.print_exc()
                break

    finally:
        print("🔴 WebSocket cleanup")
@router.websocket("/ws/system")
async def websocket_system(ws: WebSocket):
    await ws.accept()

    print("✅ WebSocket connected")

    while True:
        try:
            data = get_system_summary()
            await ws.send_json(data)
        except Exception as e:
            print("❌ WS Error:", e)

        await asyncio.sleep(2)
