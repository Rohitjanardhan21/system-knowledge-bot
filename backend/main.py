from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import os
import threading
import time
import signal

from backend.memory_engine import init_system_profile
from system_collector.collect_system import main as collect_system

# --------------------------------------------------
# 🔥 CONFIG (VERY IMPORTANT)
# --------------------------------------------------
MODE = os.getenv("SYSTEM_MODE", "server")  
# "server" → central AI system
# "agent" → node collector

COLLECT_INTERVAL = 2

running = True


# --------------------------------------------------
# INIT SYSTEM PROFILE
# --------------------------------------------------
init_system_profile()

# --------------------------------------------------
# CREATE APP
# --------------------------------------------------
app = FastAPI(title="System Intelligence Platform")

# --------------------------------------------------
# CORS
# --------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# 🔥 COLLECTOR LOOP (AGENT MODE ONLY)
# --------------------------------------------------
def collector_loop():
    global running

    print("🚀 Collector started (agent mode)...")

    while running:
        try:
            collect_system()
        except Exception as e:
            print("❌ Collector error:", e)

        time.sleep(COLLECT_INTERVAL)


# --------------------------------------------------
# 🔥 SHUTDOWN HANDLER (PRODUCTION)
# --------------------------------------------------
def shutdown_handler(signum, frame):
    global running
    print("🛑 Shutting down system...")
    running = False


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


# --------------------------------------------------
# IMPORT ROUTERS
# --------------------------------------------------
from backend.alert_routes import router as alert_router
from backend.component_routes import router as component_router
from backend.history_routes import router as history_router
from backend.simulate_routes import router as simulate_router
from backend.service_routes import router as service_router
from backend.agent_routes import router as agent_router
from backend.system_routes import router as system_router
from backend.websocket_routes import router as websocket_router
from backend.chat_routes import router as chat_router
from backend.node_routes import router as node_router  # 🔥 NEW

# --------------------------------------------------
# REGISTER ROUTERS
# --------------------------------------------------
app.include_router(alert_router, prefix="/alerts")
app.include_router(component_router, prefix="/components")
app.include_router(history_router, prefix="/history")
app.include_router(simulate_router, prefix="/simulate")
app.include_router(service_router, prefix="/services")
app.include_router(agent_router, prefix="/agents")
app.include_router(system_router, prefix="/system")
app.include_router(node_router)  # 🔥 distributed ingestion
app.include_router(websocket_router)
app.include_router(chat_router)

# --------------------------------------------------
# STARTUP
# --------------------------------------------------
@app.on_event("startup")
def startup():

    os.makedirs("system_facts", exist_ok=True)

    print("✅ System initialized")
    print("🧠 AI Intelligence Engine Running")
    print(f"🌐 Mode: {MODE}")

    # 🔥 ONLY RUN COLLECTOR IN AGENT MODE
    if MODE == "agent":
        thread = threading.Thread(target=collector_loop, daemon=True)
        thread.start()
        print("📡 Collector active (agent mode)")

    else:
        print("📡 Running as CENTRAL SERVER (no local collection)")


# --------------------------------------------------
# HEALTH (ENHANCED)
# --------------------------------------------------
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "mode": MODE,
        "collector_active": MODE == "agent"
    }


# --------------------------------------------------
# STATIC
# --------------------------------------------------
app.mount(
    "/",
    StaticFiles(directory="backend/static", html=True),
    name="static",
)
