from pathlib import Path
import json
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

STATE_PATH = Path("state/latest.json")

print("=== CONCURRENT EXECUTION SAFETY TEST ===")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Establish deterministic approved state.
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

child_code = """
from state.state_reader import get_action_state
from judgment.executor import execute_plan

action = get_action_state("free-disk-space")

result = execute_plan([action], dry_run=True)

print(result)
"""

print()
print("STARTING TWO EXECUTORS...")

p1 = subprocess.Popen(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

p2 = subprocess.Popen(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

out1, err1 = p1.communicate()
out2, err2 = p2.communicate()

print()
print("EXECUTOR 1:")
print(out1)

if err1:
    print("STDERR:", err1)

print("EXECUTOR 2:")
print(out2)

if err2:
    print("STDERR:", err2)

assert p1.returncode == 0
assert p2.returncode == 0

final_state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

final_target = next(
    a for a in final_state["actions"]
    if a.get("action") == "free-disk-space"
)

print()
print("FINAL PERSISTED STATE:")
print(
    final_target["action"],
    "|",
    final_target["status"],
    "|",
    final_target.get("execution_result"),
)

print()
print("RESULT: TEST COMPLETED")
print("Now inspect whether both executors were allowed to execute.")
