from fastapi import FastAPI, HTTPException
import json
import os
from datetime import datetime, timezone

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACTS_PATH = os.path.join(BASE_DIR, "..", "system_facts", "current.json")


def load_facts():
    if not os.path.exists(FACTS_PATH):
        raise HTTPException(503, "System facts not available")

    with open(FACTS_PATH) as f:
        return json.load(f)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/facts")
def facts():
    return load_facts()


@app.get("/facts/full")
def full_facts():
    return load_facts()


@app.get("/facts/cpu")
def cpu():
    return load_facts()["cpu"]


@app.get("/facts/memory")
def memory():
    return load_facts()["memory"]


@app.get("/facts/storage")
def storage():
    return load_facts()["storage"]


@app.get("/facts/status")
def status():
    facts = load_facts()
    collected = datetime.fromisoformat(
        facts["metadata"]["collected_at"]
    ).replace(tzinfo=timezone.utc)

    age = (datetime.now(timezone.utc) - collected).total_seconds()
    ttl = facts["metadata"]["ttl_seconds"]

    return {
        "stale": age > ttl,
        "age_seconds": int(age),
        "ttl_seconds": ttl
    }

@app.get("/facts/history")
def history():
    base = os.path.dirname(FACTS_PATH)
    hist_dir = os.path.join(base, "history")

    files = sorted(os.listdir(hist_dir))
    if len(files) < 2:
        return []

    with open(os.path.join(hist_dir, files[-2])) as f:
        prev = json.load(f)
    with open(os.path.join(hist_dir, files[-1])) as f:
        curr = json.load(f)

    return [prev, curr]
