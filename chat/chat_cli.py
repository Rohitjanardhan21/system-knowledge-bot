import json
from pathlib import Path

from agent.agent_core import handle_question
from cli.can_run import can_run
from visual.cli_timeline import render_today_timeline

FACTS_PATH = Path("system_facts/current.json")
HISTORY_DIR = Path("system_state/history")

print("System Knowledge Bot — Agent Mode (type 'exit' to quit)")


def load_facts():
    try:
        with open(FACTS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


while True:
    q = input("> ").strip()

    if not q:
        continue

    if q.lower() == "exit":
        break

    # --------------------------------------------------
    # Explicit capability / preflight commands
    # --------------------------------------------------
    if q.startswith("can-run"):
        parts = q.split(maxsplit=1)
        if len(parts) < 2:
            print("Usage: can-run <job_name>")
        else:
            can_run(parts[1])
        continue

    if q.startswith("preflight"):
        parts = q.split(maxsplit=1)
        if len(parts) < 2:
            print("Usage: preflight <workload>")
        else:
            can_run(parts[1])
        continue

    # --------------------------------------------------
    # Agent reasoning path
    # --------------------------------------------------
    facts = load_facts()

    # Signal history existence (NOT content)
    if HISTORY_DIR.exists() and any(HISTORY_DIR.glob("*.json")):
        facts["history"] = True

    response = handle_question(q, facts)

    # Always print agent text
    print(response.text)

    # Render visual only when explicitly requested
    if response.mode.value == "visual":
        render_today_timeline()
