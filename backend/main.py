# --------------------------------------------------
# 🧠 COGNITIVE SYSTEM INTELLIGENCE PLATFORM (v7.0)
# ZERO-HALLUCINATION + TRUSTED CORE
# --------------------------------------------------

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import os
import threading
import time
import logging
import json
from pathlib import Path
from collections import deque

from backend.memory_engine import init_system_profile
from system_collector.collect_system import main as collect_system
from backend.multi_agent_system import MultiAgentSystem

# 🔥 NEW (TRUST LAYER)
from backend.truth_engine import TruthEngine

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

MODE = os.getenv("SYSTEM_MODE", "server")
COLLECT_INTERVAL = int(os.getenv("COLLECT_INTERVAL", 2))
INTELLIGENCE_INTERVAL = int(os.getenv("INTELLIGENCE_INTERVAL", 3))

DATA_PATH = Path("system_facts/nodes")

# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("Cognitive-System")

# --------------------------------------------------
# GLOBAL STATE
# --------------------------------------------------

stop_event = threading.Event()
collector_thread = None
intelligence_thread = None

system_state = {
    "last_update": None,
    "status": "initializing",
    "latest_decision": None,
    "events": [],
    "intelligence": {},
    "system_feed": deque(maxlen=50),
    "decision_history": deque(maxlen=50),
    "validated": True,
    "validation_issues": []
}

# --------------------------------------------------
# ENGINE INIT
# --------------------------------------------------

cognitive_system = MultiAgentSystem()
truth_engine = TruthEngine()  # 🔥 NEW

init_system_profile()

# --------------------------------------------------
# UTILS
# --------------------------------------------------

def load_latest_metrics():
    files = sorted(DATA_PATH.glob("*.json"), reverse=True)
    if not files:
        return None

    try:
        return json.loads(files[0].read_text())
    except Exception:
        return None


def enrich_multimodal(metrics):
    return {
        **metrics,
        "audio": metrics.get("audio", []),
        "vibration": metrics.get("vibration", []),
        "temp": metrics.get("temp", metrics.get("cpu", 0))
    }


def push_feed(message):
    system_state["system_feed"].appendleft({
        "time": time.strftime("%H:%M:%S"),
        "message": message
    })


# --------------------------------------------------
# COLLECTOR LOOP
# --------------------------------------------------

def collector_loop():
    logger.info("🚀 Collector started")

    while not stop_event.is_set():
        try:
            collect_system()
            system_state["last_update"] = time.time()
        except Exception:
            logger.exception("❌ Collector error")

        stop_event.wait(COLLECT_INTERVAL)

    logger.info("🛑 Collector stopped")


# --------------------------------------------------
# 🧠 INTELLIGENCE LOOP (TRUSTED COGNITIVE CORE)
# --------------------------------------------------

def intelligence_loop():
    logger.info("🧠 Cognitive Engine Started")

    while not stop_event.is_set():
        try:
            metrics = load_latest_metrics()
            if not metrics:
                continue

            metrics = enrich_multimodal(metrics)

            system_state["status"] = "analyzing"

            # --------------------------------------------------
            # 🧠 RUN SYSTEM
            # --------------------------------------------------
            result = cognitive_system.autonomous_loop(metrics)

            decision = result.get("decision", {})
            features = result.get("features", {})
            anomaly_score = result.get("anomaly_score", 0)

            # --------------------------------------------------
            # 🔥 TRUTH VALIDATION (CRITICAL)
            # --------------------------------------------------
            validation = truth_engine.validate(metrics, features, decision)

            system_state["validated"] = validation["valid"]
            system_state["validation_issues"] = validation["issues"]

            # --------------------------------------------------
            # 🔥 SAFE CONFIDENCE ADJUSTMENT
            # --------------------------------------------------
            if not validation["valid"]:
                decision["confidence"] = min(decision.get("confidence", 0.5), 0.6)

            # --------------------------------------------------
            # 🔥 UPDATE STATE
            # --------------------------------------------------
            system_state["intelligence"] = result
            system_state["latest_decision"] = decision
            system_state["events"] = result.get("events", [])

            # --------------------------------------------------
            # 🔥 DECISION MEMORY
            # --------------------------------------------------
            system_state["decision_history"].appendleft({
                "time": time.time(),
                "action": decision.get("action"),
                "confidence": decision.get("confidence"),
                "validated": validation["valid"]
            })

            # --------------------------------------------------
            # 🔥 SYSTEM FEED (INTELLIGENT)
            # --------------------------------------------------
            push_feed(f"CPU {metrics.get('cpu')}% analyzed")

            if anomaly_score > 1.5:
                push_feed("⚠ High anomaly detected")

            for e in result.get("events", []):
                push_feed(e)

            push_feed(f"Decision: {decision.get('action')}")

            if not validation["valid"]:
                push_feed("⚠ Decision downgraded (validation failed)")

            # --------------------------------------------------
            # 🤖 SAFE AUTONOMOUS EXECUTION
            # --------------------------------------------------
            if decision.get("auto_execute") and validation["valid"]:
                logger.warning(f"⚡ AUTO ACTION: {decision['action']}")
                push_feed(f"AUTO EXECUTION: {decision['action']}")

            elif decision.get("auto_execute"):
                push_feed("🚫 Auto execution blocked (unsafe)")

        except Exception:
            logger.exception("❌ Intelligence error")

        stop_event.wait(INTELLIGENCE_INTERVAL)

    logger.info("🛑 Intelligence stopped")


# --------------------------------------------------
# LIFESPAN
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global collector_thread, intelligence_thread

    os.makedirs("system_facts/nodes", exist_ok=True)

    logger.info("✅ System Initialized")
    logger.info("🧠 Cognitive Platform Booting")
    logger.info(f"🌐 Mode: {MODE}")

    if MODE == "agent":
        collector_thread = threading.Thread(
            target=collector_loop,
            daemon=True
        )
        collector_thread.start()
        logger.info("📡 Collector active")

    intelligence_thread = threading.Thread(
        target=intelligence_loop,
        daemon=True
    )
    intelligence_thread.start()

    yield

    logger.warning("⚠️ Shutdown initiated")
    stop_event.set()

    if collector_thread:
        collector_thread.join(timeout=5)

    if intelligence_thread:
        intelligence_thread.join(timeout=5)

    logger.info("🛑 Shutdown complete")


# --------------------------------------------------
# APP
# --------------------------------------------------

app = FastAPI(
    title="Cognitive System Intelligence Platform",
    version="7.0",
    lifespan=lifespan
)

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
# ROUTERS
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
from backend.node_routes import router as node_router
from backend.ai_routes import router as ai_router

app.include_router(alert_router, prefix="/alerts")
app.include_router(component_router, prefix="/components")
app.include_router(history_router, prefix="/history")
app.include_router(simulate_router, prefix="/simulate")
app.include_router(service_router, prefix="/services")
app.include_router(agent_router, prefix="/agents")

app.include_router(system_router, prefix="/system")

app.include_router(node_router)
app.include_router(websocket_router)
app.include_router(chat_router)
app.include_router(ai_router, prefix="/ai")

# --------------------------------------------------
# STATUS
# --------------------------------------------------

@app.get("/status")
def system_status():
    return system_state


# --------------------------------------------------
# HEALTH
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": MODE,
        "timestamp": time.time(),
        "validated": system_state["validated"],
        "note": "Trusted cognitive loop active"
    }


# --------------------------------------------------
# STATIC
# --------------------------------------------------

if os.path.exists("backend/static"):
    app.mount(
        "/",
        StaticFiles(directory="backend/static", html=True),
        name="static",
    )
