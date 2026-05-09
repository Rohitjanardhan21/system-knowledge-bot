# ── Silent Degradation endpoint ───────────────────────────────────────────────
# Add this block to backend/main.py near the other /cognitive/ endpoints

@app.get("/cognitive/degradation", tags=["Cognitive"])
async def cognitive_degradation():
    """
    Returns long-term chronic drift analysis.
    Requires ~7 days of data for meaningful results.
    """
    try:
        from backend.core.cognitive.degradation import get_degradation_detector
        return get_degradation_detector().get_report_dict()
    except Exception as e:
        return {
            "is_degrading": False,
            "summary": "Degradation detector initialising — check back after 7 days of data.",
            "has_data": False,
            "days_of_data": 0,
            "metrics": [],
            "error": str(e),
        }
