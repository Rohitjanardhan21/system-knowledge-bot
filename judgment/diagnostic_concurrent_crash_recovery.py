from pathlib import Path
import json
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.recovery import recover_interrupted_actions

STATE_PATH = Path("state/latest.json")

print("=== CONCURRENT CRASH → RECOVERY TEST ===")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "approved"
target.pop("execution_started_at", None)
target.pop("execution_completed_at", None)
target.pop("execution_result", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("INITIAL:")
print(target["action"], "|", target["status"])

child_code = r'''
from pathlib import Path
import json
import os
import sys

from judgment.lifecycle import begin_execution

STATE_PATH = Path("state/latest.json")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

action = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

result = begin_execution(action)

print("CHILD CLAIM:")
print(result, flush=True)

if result.get("status") != "executing":
    sys.exit(1)

print("SIMULATED CRASH AFTER EXECUTION CLAIM", flush=True)

os._exit(99)
'''

print()
print("STARTING CRASHING EXECUTOR...")

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print("CHILD OUTPUT:")
print(child.stdout)

assert child.returncode == 99

persisted = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

persisted_target = next(
    a for a in persisted["actions"]
    if a.get("action") == "free-disk-space"
)

print()
print("STATE AFTER CRASH:")
print(
    persisted_target["action"],
    "|",
    persisted_target["status"],
)

assert persisted_target["status"] == "executing"

print()
print("RUNNING RESTART RECOVERY...")

recovered = recover_interrupted_actions()

print("RECOVERED:", recovered)

assert "free-disk-space" in recovered

final_state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

final_target = next(
    a for a in final_state["actions"]
    if a.get("action") == "free-disk-space"
)

print()
print("FINAL STATE:")
print(
    final_target["action"],
    "|",
    final_target["status"],
    "|",
    final_target.get("execution_result"),
)

assert final_target["status"] == "failed"
assert final_target["execution_result"] == "interrupted-by-restart"

print()
print("RESULT: PASS")
print("Execution claim survived the crashing process.")
print("Restart recovery detected the interrupted execution.")
print("Interrupted execution became failed.")
print("The crashed action was not falsely marked executed.")
