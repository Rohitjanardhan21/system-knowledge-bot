import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACTS_PATH = os.path.join(BASE_DIR, "..", "system_facts", "baseline.json")

def load_baseline():
    """
    Loads baseline system metrics.
    If none exist yet, returns an empty dict.
    """
    if not os.path.exists(FACTS_PATH):
        return {}

    with open(FACTS_PATH) as f:
        return json.load(f)
