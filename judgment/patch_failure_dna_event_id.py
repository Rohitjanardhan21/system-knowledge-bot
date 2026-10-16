from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from safe_patch import write_text_safely

path = ROOT / "backend" / "core" / "cognitive" / "failure_dna.py"
APPLY = "--apply" in sys.argv
source = path.read_text(encoding="utf-8")

old_import = "import json, os, time, threading"
new_import = "import json, os, time, threading, uuid"

old_id = 'event_id = f"{event_type}_{int(time.time())}"'
new_id = 'event_id = f"{event_type}_{uuid.uuid4().hex}"'

if old_import not in source and new_import not in source:
    raise SystemExit("PATCH ERROR: expected import line not found")
if old_id not in source and new_id not in source:
    raise SystemExit("PATCH ERROR: expected event_id line not found")

if old_import in source:
    source = source.replace(old_import, new_import, 1)
if old_id in source:
    source = source.replace(old_id, new_id, 1)

write_text_safely(path, source, apply=APPLY)

print("PATCH PREVIEW COMPLETE" if not APPLY else "PATCH APPLIED")
print("Import:", new_import)
print("Event ID:", new_id)
