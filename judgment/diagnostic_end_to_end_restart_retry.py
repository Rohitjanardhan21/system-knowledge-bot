from pathlib import Path
import json
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)
import subprocess
import sys

from judgment.lifecycle import retry_failed_action
from judgment.executor import execute_plan
from judgment.audit import load_audit

STATE_PATH = Path("state/latest.json")

print("=== END-TO-END CRASH → RECOVERY → RETRY TEST ===")

# ---------------------------------------------------------
# 1. Establish a deterministic failed action
# ---------------------------------------------------------
state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

target["status"] = "failed"
target["execution_result"] = "simulated-previous-failure"
target.pop("execution_started_at", None)
target.pop("execution_completed_at", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. INITIAL FAILED STATE:")
print(target["action"], "|", target["status"])

# ---------------------------------------------------------
# 2. Explicit retry approval
# ---------------------------------------------------------
retry = retry_failed_action(target)

print()
print("2. RETRY APPROVAL:")
print(retry)

assert retry["status"] == "approved"
assert target["status"] == "approved"

# ---------------------------------------------------------
# 3. Start execution
# ---------------------------------------------------------
result = execute_plan([target], dry_run=True)

print()
print("3. EXECUTION BEFORE RESTART:")
print(result)

assert result[0]["status"] == "simulated"
persisted_after_execution = json.loads(STATE_PATH.read_text(encoding="utf-8"))
persisted_target = next(a for a in persisted_after_execution["actions"] if a.get("action") == "free-disk-space")
assert persisted_target["status"] == "executed"
# ---------------------------------------------------------
# 4. Verify persisted executed state
# ---------------------------------------------------------
persisted = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

persisted_target = next(
    a for a in persisted["actions"]
    if a.get("action") == "free-disk-space"
)

print()
print("4. PERSISTED STATE:")
print(
    persisted_target["action"],
    "|",
    persisted_target["status"],
    "|",
    persisted_target.get("execution_result"),
)

assert persisted_target["status"] == "executed"

# ---------------------------------------------------------
# 5. Fresh process attempts execution
# ---------------------------------------------------------
child_code = """
from state.state_reader import get_action_state
from judgment.executor import execute_plan

action = get_action_state("free-disk-space")

print("CHILD STATE:")
print(action)

result = execute_plan([action], dry_run=True)

print("CHILD EXECUTION:")
print(result)

assert result[0]["status"] == "blocked"
assert result[0]["result"] == "already-executed"
"""

child = subprocess.run(
    [sys.executable, "-c", child_code],
    cwd=Path.cwd(),
    capture_output=True,
    text=True,
)

print()
print("5. FRESH PROCESS:")
print(child.stdout)

if child.returncode != 0:
    print(child.stderr)
    raise SystemExit(child.returncode)

# ---------------------------------------------------------
# 6. Verify audit sequence
# ---------------------------------------------------------
audit = load_audit()

recent = [
    entry for entry in audit
    if entry.get("action") == "free-disk-space"
][-10:]

print()
print("6. AUDIT:")

for entry in recent:
    print(
        f"{entry.get('event'):22} | "
        f"{entry.get('status'):12} | "
        f"{entry.get('result'):28} | "
        f"{entry.get('action')}"
    )

events = [entry.get("event") for entry in recent]

assert "retry-approved" in events
assert "execution-started" in events
assert "execution-completed" in events

print()
print("RESULT: PASS")
print("Failed action was explicitly retried.")
print("Execution completed and persisted.")
print("Fresh process could not duplicate execution.")
print("Lifecycle audit remained durable.")

