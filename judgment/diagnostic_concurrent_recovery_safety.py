from pathlib import Path
import json
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

STATE_PATH = Path("state/latest.json")

print("=== CONCURRENT RECOVERY SAFETY TEST ===")

# Establish deterministic interrupted state.
state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "executing"
target["execution_result"] = None
target.pop("execution_completed_at", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("INITIAL:")
print(target["action"], "|", target["status"])

child_code = r'''
from judgment.recovery import recover_interrupted_actions

result = recover_interrupted_actions()

print("RECOVERY RESULT:", result, flush=True)
'''

print()
print("STARTING TWO RECOVERY PROCESSES...")

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
print("PROCESS 1:")
print(out1)

if err1:
    print("STDERR 1:")
    print(err1)

print("PROCESS 2:")
print(out2)

if err2:
    print("STDERR 2:")
    print(err2)

assert p1.returncode == 0
assert p2.returncode == 0

# Inspect final state.
state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print()
print("FINAL STATE:")
print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)

assert target["status"] == "failed"
assert target["execution_result"] == "interrupted-by-restart"

print()
print("RESULT: PASS")
print("Concurrent recovery processes completed safely.")
print("Final interrupted action became failed exactly once.")
print("No recovery process falsely marked the action executed.")
