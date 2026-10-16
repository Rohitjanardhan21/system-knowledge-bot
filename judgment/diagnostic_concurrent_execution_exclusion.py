from pathlib import Path
import json
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

STATE_PATH = Path("state/latest.json")

print("=== CONCURRENT EXECUTION EXCLUSION TEST ===")

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
import json
import time
from pathlib import Path
from judgment.lifecycle import begin_execution, complete_execution

STATE_PATH = Path("state/latest.json")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
action = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

started = begin_execution(action)

print("BEGIN:", started, flush=True)

if started.get("status") == "executing":
    time.sleep(1.0)

    completed = complete_execution(
        action,
        success=True,
        result="concurrent-test-success",
    )

    print("COMPLETE:", completed, flush=True)
'''

print()
print("STARTING TWO PROCESSES SIMULTANEOUSLY...")

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

print("PROCESS 2:")
print(out2)

if err1:
    print("PROCESS 1 ERROR:")
    print(err1)

if err2:
    print("PROCESS 2 ERROR:")
    print(err2)

assert p1.returncode == 0
assert p2.returncode == 0

combined = out1 + out2

executing_count = combined.count("'status': 'executing'")
blocked_count = combined.count("already executing")

print()
print("EXECUTING CLAIMS:", executing_count)
print("BLOCKED CLAIMS:", blocked_count)

assert executing_count == 1, (
    f"Expected exactly one execution claim, got {executing_count}"
)

assert blocked_count == 1, (
    f"Expected exactly one blocked concurrent claim, got {blocked_count}"
)

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
    final_target.get("action"),
    "|",
    final_target.get("status"),
    "|",
    final_target.get("execution_result"),
)

assert final_target["status"] == "executed"

print()
print("RESULT: PASS")
print("Exactly one executor acquired the execution claim.")
print("The competing executor was blocked.")
print("Final state is executed.")
print("Concurrent duplicate execution is prevented.")
