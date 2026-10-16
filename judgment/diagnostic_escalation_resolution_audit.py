import json
from judgment.audit import load_audit
from judgment.recovery import STATE_PATH
from judgment.retry import resolve_escalation
from judgment._test_auth import ADMIN_PRINCIPAL

print("=== ESCALATION RESOLUTION AUDIT INVARIANT TEST ===")

ACTION = "free-disk-space"

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
target = next(a for a in state["actions"] if a.get("action") == ACTION)

target["status"] = "failed"
target["retry_count"] = 2
target["max_retries"] = 2
target["escalation_required"] = True
target["execution_result"] = "retry-limit-reached"

STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
before_audit = load_audit()

print("\n1. INITIAL ESCALATED STATE:")
print(ACTION, "|", target["status"], "| retry_count =", target["retry_count"], "| escalation =", target["escalation_required"])
print("PASS")

print("\n2. EXPLICIT ESCALATION RESOLUTION:")
result = resolve_escalation(ACTION, principal=ADMIN_PRINCIPAL)
print(result)
assert result["status"] == "approved"
assert result["retry_count"] == 0
assert result["escalation_required"] is False
print("PASS")

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
target = next(a for a in state["actions"] if a.get("action") == ACTION)

print("\n3. DURABLE STATE:")
print(ACTION, "|", target["status"], "| retry_count =", target["retry_count"], "| escalation =", target["escalation_required"])
assert target["status"] == "approved"
assert target["retry_count"] == 0
assert target["escalation_required"] is False
print("PASS")

after_audit = load_audit()
new_events = after_audit[len(before_audit):]

resolution_events = [
    e for e in new_events
    if e.get("action") == ACTION and e.get("event") == "escalation-resolved"
]

assert len(resolution_events) == 1
resolution = resolution_events[0]

assert resolution["status"] == "approved"
assert resolution["result"] == "escalation-resolved"
assert resolution["retry_count"] == 0
assert resolution["escalation_required"] is False

print("\n4. AUDIT CHECK:")
print(resolution["event"], "|", resolution["status"], "|", resolution["result"], "| retry_count =", resolution["retry_count"], "| escalation =", resolution["escalation_required"])
print("PASS")

assert resolution["status"] == target["status"]
assert resolution["retry_count"] == target["retry_count"]
assert resolution["escalation_required"] == target["escalation_required"]

print("\n5. AUDIT ↔ STATE INVARIANT:")
print("STATE:", target["status"], "| AUDIT:", resolution["status"])
print("RETRY COUNT:", target["retry_count"], "| AUDIT:", resolution["retry_count"])
print("ESCALATION:", target["escalation_required"], "| AUDIT:", resolution["escalation_required"])
print("PASS")

print("\nRESULT: PASS")
print("Escalation resolution is explicitly audited.")
print("Exactly one resolution audit event was generated.")
print("Audit metadata matches durable state.")
