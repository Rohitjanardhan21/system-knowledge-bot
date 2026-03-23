from fastapi import APIRouter, HTTPException
from pathlib import Path
import json

from backend.metric_normalizer import normalize_metrics
from backend.trend_engine import compute_trends
from backend.forecast_engine import compute_forecast
from backend.posture_engine import compute_posture
from backend.history_engine import load_yesterday_snapshot, load_history
from backend.temporal_engine import temporal_analysis
from backend.causal_engine import detect_causal_relationship
from backend.decision_engine import compute_decision
from backend.root_cause_engine import detect_root_cause
from backend.anomaly_engine import detect_anomalies
from backend.explanation_engine import generate_explanation
from backend.recommendation_engine import generate_recommendation
from backend.alert_engine import (
    register_alerts,
    load_alerts,
)

router = APIRouter()

CURRENT_FILE = Path("system_facts/current.json")


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def load_current_snapshot():
    if not CURRENT_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="No current system snapshot available",
        )

    try:
        return json.loads(CURRENT_FILE.read_text())
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read current snapshot: {e}",
        )


# ---------------------------------------------------------
# /system/summary
# ---------------------------------------------------------
@router.get("/system/summary")
def system_summary():

    # ---------------------------
    # Load snapshot
    # ---------------------------
    raw_snapshot = load_current_snapshot()

    # ---------------------------
    # Normalize
    # ---------------------------
    flat_metrics = normalize_metrics(raw_snapshot)

    # ---------------------------
    # Trends + Forecast
    # ---------------------------
    trends = compute_trends()
    forecast = compute_forecast(trends)

    # ---------------------------
    # Posture
    # ---------------------------
    posture = compute_posture(flat_metrics, forecast)

    # ---------------------------
    # Yesterday snapshot
    # ---------------------------
    yesterday = load_yesterday_snapshot()

    # ---------------------------
    # Full History
    # ---------------------------
    history = load_history()

    # ---------------------------
    # Temporal Analysis
    # ---------------------------
    temporal = temporal_analysis(history)

    # ---------------------------
    # Causal Analysis
    # ---------------------------
    causal = detect_causal_relationship(flat_metrics, temporal)

    # Anomalies + Alerts
    anomalies = detect_anomalies(flat_metrics)
    alerts = register_alerts(anomalies)

    # Decision Engine
    decision = compute_decision(flat_metrics, forecast, anomalies, causal)
    # ---------------------------
    # Confidence Score
    # ---------------------------
    if anomalies:
        total_conf = sum(a.get("confidence", 0.5) for a in anomalies)
        confidence_score = round(1.0 - min(1.0, total_conf / 3.0), 2)
    else:
        confidence_score = 1.0

    # ---------------------------
    # Root Cause
    # ---------------------------
    root_cause = detect_root_cause()

    # ---------------------------
    # Explanation + Recommendation
    # ---------------------------
    explanation = generate_explanation(
        flat_metrics.get("cpu_pct"),
        anomalies,
        root_cause
    )

    # Add causal reasoning into explanation
    if causal and causal.get("type") != "unknown":
        explanation += f" Likely cause: {causal.get('reason')}."

    recommendation = generate_recommendation(
        anomalies,
        root_cause
    )

    # ---------------------------
    # Final Response
    # ---------------------------
    return {
        "cpu": flat_metrics.get("cpu_pct"),
        "memory": flat_metrics.get("mem_pct"),
        "disk": flat_metrics.get("disk_pct"),
        "network": flat_metrics.get("network"),

        "trends": trends,
        "forecast": forecast,
        "posture": posture,

        # 🔥 Intelligence Layers
        "temporal": temporal,
        "causal": causal,
        "decision": decision,

        "workload_score": forecast.get("risk_score"),
        "yesterday": yesterday,

        "anomalies": anomalies,
        "alerts": alerts,
        "confidence_score": confidence_score,

        "root_cause": root_cause,

        "explanation": explanation,
        "recommendation": recommendation,
    }


# ---------------------------------------------------------
# /alerts/active
# ---------------------------------------------------------

@router.get("/alerts/active")
def get_active_alerts():
    return load_alerts()


# ---------------------------------------------------------
# Health check
# ---------------------------------------------------------

@router.get("/health")
def health_check():
    return {"status": "ok"}
