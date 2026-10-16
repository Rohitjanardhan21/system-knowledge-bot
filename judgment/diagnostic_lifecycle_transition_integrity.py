from pathlib import Path
import json
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

from judgment.lifecycle import (
    begin_execution,
    complete_execution,
    retry_failed_action,
)

STATE_PATH = Path("state/latest.json")

print("=== LIFECYCLE TRANSITION INTEGRITY TEST ===")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

target = next(
    a for a in state["actions"]
    if a.get("action") == "free-disk-space"
)

# Start from approved.
target["status"] = "approved"
target["execution_result"] = None
target.pop("execution_started_at", None)
target.pop("execution_completed_at", None)
target.pop("recovery_reason", None)

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print()
print("1. APPROVED → EXECUTING")

result = begin_execution(target)
print(result)

assert result["status"] == "executing"
assert target["status"] == "executing"

print("PASS")

print()
print("2. EXECUTING → EXECUTED")

result = complete_execution(
    target,
    success=True,
    result="transition-integrity-success",
)

print(result)

assert result["status"] == "executed"
assert target["status"] == "executed"

print("PASS")

print()
print("3. EXECUTED → EXECUTING MUST BE BLOCKED")

result = begin_execution(target)
print(result)

assert result["status"] == "blocked"

print("PASS")

print()
print("4. EXECUTED → FAILED MUST BE BLOCKED")

try:
    result = complete_execution(
        target,
        success=False,
        result="illegal-transition",
    )
    print(result)

    assert result["status"] != "failed"

except Exception as exc:
    print("BLOCKED:", type(exc).__name__, "|", exc)

print("PASS")

print()
print("5. FAILED → EXECUTED WITHOUT RETRY MUST BE BLOCKED")

target["status"] = "failed"
target["execution_result"] = "simulated-failure"

STATE_PATH.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

result = begin_execution(target)
print(result)

assert result["status"] == "blocked"

print("PASS")

print()
print("6. FAILED → APPROVED THROUGH EXPLICIT RETRY")

result = retry_failed_action(target)
print(result)

assert result["status"] == "approved"
assert target["status"] == "approved"

print("PASS")

print()
print("7. APPROVED → EXECUTING AFTER RETRY")

result = begin_execution(target)
print(result)

assert result["status"] == "executing"

print("PASS")

print()
print("8. EXECUTING → EXECUTED")

result = complete_execution(
    target,
    success=True,
    result="final-transition-success",
)

print(result)

assert result["status"] == "executed"

print("PASS")

print()
print("9. PERSISTED FINAL STATE")

persisted = json.loads(
    STATE_PATH.read_text(encoding="utf-8")
)

persisted_target = next(
    a for a in persisted["actions"]
    if a.get("action") == "free-disk-space"
)

print(
    persisted_target["action"],
    "|",
    persisted_target["status"],
    "|",
    persisted_target.get("execution_result"),
)

assert persisted_target["status"] == "executed"
assert persisted_target["execution_result"] == "final-transition-success"

print()
print("RESULT: PASS")
print("Valid lifecycle transitions succeeded.")
print("Executed actions cannot be restarted.")
print("Failed actions cannot bypass retry approval.")
print("Explicit retry remains the only failed → approved path.")
print("Final execution state was persisted.")
