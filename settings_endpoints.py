
# ── Settings endpoints ────────────────────────────────────────────────────────
# Paste this block into backend/main.py before the _FRONTEND_DIR block

from backend.core.settings import settings_manager as _sm

@app.get("/settings", tags=["Settings"])
async def get_settings():
    return _sm.get_all()

@app.post("/settings", tags=["Settings"])
async def save_settings(request: Request):
    body = await request.json()
    result = _sm.save(body)
    # Apply thresholds to live alert engine immediately
    try:
        _sm.apply_alert_thresholds(get_alert_engine())
    except Exception:
        pass
    return result

@app.post("/settings/reset", tags=["Settings"])
async def reset_settings():
    return _sm.reset()

@app.post("/settings/test-email", tags=["Settings"])
async def settings_test_email():
    try:
        from backend.core.reports.weekly_report import send_alert_email
        send_alert_email(
            severity="INFO",
            message="CVIS settings test — email delivery confirmed.",
            reason="Manual test from Settings panel",
            actions=["No action required"],
            metrics={
                "cpu_percent":  _last_metrics.get("cpu_percent",  0),
                "memory":       _last_metrics.get("memory",       0),
                "health_score": _last_metrics.get("health_score", 100),
            },
        )
        return {"success": True, "message": "Test email sent — check your inbox."}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/settings/send-report", tags=["Settings"])
async def settings_send_report():
    try:
        from backend.core.reports.weekly_report import send_weekly_report_email
        to = _sm.get("alert_email") or os.environ.get("ALERT_EMAIL", "")
        if not to:
            return {"success": False, "message": "No alert email configured."}
        send_weekly_report_email(to)
        return {"success": True, "message": f"Weekly report sent to {to}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
