# ── Stress Test endpoints ─────────────────────────────────────────────────────
# Inject into backend/main.py before the _FRONTEND_DIR block

@app.get("/stress/scenarios", tags=["Demo"])
async def list_stress_scenarios():
    """List available stress test scenarios for demo."""
    try:
        from backend.core.demo.stress_engine import get_scenarios
        return get_scenarios()
    except Exception as e:
        return []

@app.post("/stress/start/{scenario_id}", tags=["Demo"])
async def start_stress(scenario_id: str):
    """Start a stress scenario to trigger CVIS predictions."""
    try:
        from backend.core.demo.stress_engine import start_scenario
        return start_scenario(scenario_id)
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/stress/stop/{scenario_id}", tags=["Demo"])
async def stop_stress(scenario_id: str):
    """Stop a running stress scenario."""
    try:
        from backend.core.demo.stress_engine import stop_scenario
        return stop_scenario(scenario_id)
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/stress/stop", tags=["Demo"])
async def stop_all_stress():
    """Stop all running stress scenarios immediately."""
    try:
        from backend.core.demo.stress_engine import stop_all
        return stop_all()
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/stress/status", tags=["Demo"])
async def stress_status():
    """Get current stress test status."""
    try:
        from backend.core.demo.stress_engine import get_status
        return get_status()
    except Exception as e:
        return {"running": False, "active": [], "error": str(e)}
