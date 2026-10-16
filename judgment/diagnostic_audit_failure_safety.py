import json
from pathlib import Path

from judgment.lifecycle import begin_execution, complete_execution

STATE_PATH = Path("state") / "latest.json"

print("=== AUDIT FAILURE SAFETY TEST ===")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Establish a clean approved state.
target["status"] = "approved"
target["execution_result"] = None
target.pop("execution_started_at", None)
target.pop("execution_completed_at", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. INITIAL STATE:")
print(target["action"], "|", target["status"])
assert target["status"] == "approved"
print("PASS")

# Inject an audit failure into the lifecycle module.
import judgment.lifecycle as lifecycle

original_record_execution = lifecycle.record_execution


def failing_audit(*args, **kwargs):
    raise RuntimeError("simulated-audit-write-failure")


lifecycle.record_execution = failing_audit

print()
print("2. INJECTED AUDIT FAILURE:")

start = None

try:
    start = begin_execution(target)
    print("BEGIN RESULT:", start)
except Exception as exc:
    print(
        "BEGIN EXCEPTION:",
        type(exc).__name__,
        "|",
        str(exc),
    )

# Restore audit function before inspection.
lifecycle.record_execution = original_record_execution

print()
print("3. DURABLE STATE AFTER AUDIT FAILURE:")

state = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    target["action"],
    "|",
    target["status"],
    "|",
    target.get("execution_result"),
)

print()
print("4. SAFETY CHECK:")

# The key invariant:
# an audit failure must not make a successful execution claim
# disappear into an inconsistent terminal state.
assert target["status"] in {
    "executing",
    "failed",
    "approved",
}

assert target["status"] != "executed"

print("PASS")

print()
print("RESULT: PASS")
print("Audit failure did not create a false executed state.")
print("Durable lifecycle state remains non-successful.")
print("Audit failure cannot silently manufacture execution success.")
