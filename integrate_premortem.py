# CVIS Pre-Mortem — Integration Instructions
# ============================================
# 1. Copy premortem.py to backend/core/cognitive/premortem.py
# 2. Add the import to backend/main.py
# 3. Add the ingest call to the metric loop
# 4. Add the API endpoint
# Run this script to apply steps 2-4 automatically.

import re

MAIN_PATH = "backend/main.py"

with open(MAIN_PATH) as f:
    src = f.read()

# ── Step 1: Add import ──
old_import = "from backend.core.cognitive.forecaster import get_forecaster"
new_import = (
    "from backend.core.cognitive.forecaster  import get_forecaster\n"
    "from backend.core.cognitive.premortem   import get_premortem_engine"
)

if old_import in src:
    src = src.replace(old_import, new_import)
    print("✅ Import added")
else:
    print("⚠ Import line not found — add manually:")
    print("  from backend.core.cognitive.premortem import get_premortem_engine")

# ── Step 2: Add ingest call in metric loop ──
# Find where forecaster.ingest is called and add premortem.ingest next to it
old_ingest = "get_forecaster().ingest(metrics)"
new_ingest = (
    "get_forecaster().ingest(metrics)\n"
    "            get_premortem_engine().ingest(metrics)"
)

if old_ingest in src:
    src = src.replace(old_ingest, new_ingest)
    print("✅ Ingest call added to metric loop")
else:
    print("⚠ Ingest line not found — add manually next to get_forecaster().ingest(metrics):")
    print("  get_premortem_engine().ingest(metrics)")

# ── Step 3: Add API endpoint ──
# Add after the /cognitive/forecast endpoint
old_endpoint = '@app.get("/cognitive/forecast"'
new_endpoint_block = '''
@app.get("/cognitive/premortem", tags=["Cognitive"])
async def cognitive_premortem():
    """
    Failure Pre-Mortem — What will kill this machine in the next 30 days?
    
    Unlike predictions (next 60 min), the pre-mortem looks weeks ahead
    using trend analysis to identify slow-moving threats before they
    become emergencies.
    
    Returns threats sorted by urgency with plain English explanations,
    evidence, probability estimates, and specific recommendations.
    """
    import dataclasses
    from backend.core.cognitive.premortem import get_premortem_engine
    
    dna = get_dna_engine().get_dna_summary()
    result = get_premortem_engine().run(dna_summary=dna)
    
    def threat_to_dict(t):
        return {
            "threat_id":      t.threat_id,
            "failure_type":   t.failure_type,
            "probability":    round(t.probability * 100, 1),
            "days_until":     round(t.days_until, 1) if t.days_until else None,
            "confidence":     t.confidence,
            "headline":       t.headline,
            "evidence":       t.evidence,
            "recommendation": t.recommendation,
            "data_points":    t.data_points,
            "trend_per_day":  round(t.trend_per_day, 3),
        }
    
    return {
        "generated_at":  result.generated_at,
        "horizon_days":  result.horizon_days,
        "safe":          result.safe,
        "summary":       result.plain_summary,
        "data_quality":  result.data_quality,
        "snapshot_count": result.snapshot_count,
        "threat_count":  len(result.threats),
        "threats":       [threat_to_dict(t) for t in result.threats],
        "top_threat":    threat_to_dict(result.top_threat) if result.top_threat else None,
    }

'''

if old_endpoint in src:
    src = src.replace(old_endpoint, new_endpoint_block + old_endpoint)
    print("✅ API endpoint added before /cognitive/forecast")
else:
    print("⚠ Endpoint injection point not found")

with open(MAIN_PATH, "w") as f:
    f.write(src)

print()
print("═══════════════════════════════════════════════")
print("  Integration complete.")
print("  Now rebuild Docker:")
print("  docker compose down && docker compose up -d --build backend")
print("  Then test:")
print("  curl -s http://localhost:8000/cognitive/premortem | python3 -m json.tool")
print("═══════════════════════════════════════════════")
