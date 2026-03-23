from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
# -------------------------------------------------
# CREATE APP FIRST (CRITICAL)
# -------------------------------------------------

app = FastAPI(title="System Knowledge Bot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all (dev mode)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
                   )
# -------------------------------------------------
# ROUTERS
# -------------------------------------------------
from backend.alert_routes import router as alert_router
from backend.component_routes import router as component_router
from backend.history_routes import router as history_router
from backend.simulate_routes import router as simulate_router
from backend.service_routes import router as service_router
from backend.agent_routes import router as agent_router
from backend.system_routes import router as system_router
from backend.temporal_engine import temporal_analysis
# register routers
app.include_router(alert_router)
app.include_router(component_router)
app.include_router(history_router)
app.include_router(simulate_router)
app.include_router(service_router)
app.include_router(agent_router)
app.include_router(system_router)

# -------------------------------------------------
# STATIC FRONTEND
# -------------------------------------------------

app.mount(
    "/",
    StaticFiles(directory="backend/static", html=True),
    name="static",
)
