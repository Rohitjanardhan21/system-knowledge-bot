MAIN_PATH = "backend/main.py"

with open(MAIN_PATH) as f:
    src = f.read()

applied = []

old2 = "from backend.core.cognitive.premortem    import get_premortem_engine"
new2 = old2 + "\nfrom backend.core.actions.auto_remediation   import get_ar_engine"
if old2 in src and "auto_remediation" not in src:
    src = src.replace(old2, new2)
    applied.append("✅ Import added")
else:
    applied.append("⚠ Import skipped")

old_ingest = "                    get_premortem_engine().ingest(m)"
new_ingest = old_ingest + "\n                    get_ar_engine().update_metrics(m)"
if old_ingest in src and "update_metrics" not in src:
    src = src.replace(old_ingest, new_ingest)
    applied.append("✅ Metrics wired")
else:
    applied.append("⚠ Metrics skipped")

old_pred = "active_pred = dna.predict(m)"
new_pred = (old_pred + "\n"
    "                    try:\n"
    "                        ar=get_ar_engine();ar.set_notifier(get_notifier())\n"
    "                        preds=dna.get_active_predictions()\n"
    "                        dna_sum=dna.get_dna_summary()\n"
    "                        pred_dicts=[{'id':p.prediction_id,'type':p.failure_type,'confidence':p.confidence*100,'severity':p.severity,'message':p.plain_message,'acknowledged':p.acknowledged,'resolved':p.resolved} for p in preds]\n"
    "                        ar.evaluate(pred_dicts,dna_sum)\n"
    "                    except Exception:\n"
    "                        pass\n"
)
if old_pred in src and "ar.evaluate" not in src:
    src = src.replace(old_pred, new_pred)
    applied.append("✅ AR evaluation wired")
else:
    applied.append("⚠ Predict skipped")

old_ep = '@app.get("/cognitive/premortem"'
new_eps = '@app.get("/cognitive/remediation/status",tags=["Actions"])\nasync def remediation_status():\n    return get_ar_engine().get_status()\n\n@app.get("/cognitive/remediation/log",tags=["Actions"])\nasync def remediation_log(limit:int=20):\n    return get_ar_engine().get_audit_log(limit=limit)\n\n' + old_ep
if old_ep in src and "remediation_status" not in src:
    src = src.replace(old_ep, new_eps)
    applied.append("✅ Endpoints added")
else:
    applied.append("⚠ Endpoints skipped")

with open(MAIN_PATH, "w") as f:
    f.write(src)

for a in applied:
    print(a)
