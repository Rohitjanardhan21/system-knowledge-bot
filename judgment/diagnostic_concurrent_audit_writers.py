from pathlib import Path
import json
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from judgment.diagnostic_sandbox import run_isolated_diagnostic

    run_isolated_diagnostic(__file__)

AUDIT_PATH = Path("state/audit.json")

print("=== CONCURRENT AUDIT WRITER SAFETY TEST ===")

baseline = [
    {
        "event": "baseline",
        "status": "approved",
        "action": "free-disk-space",
        "result": "baseline-audit",
    }
]

AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
AUDIT_PATH.write_text(
    json.dumps(baseline, indent=2),
    encoding="utf-8",
)

child_code = r'''
from judgment.audit import record_execution

result = record_execution({
    "event": "execution-completed",
    "status": "executed",
    "action": "free-disk-space",
    "result": "concurrent-audit-writer",
})

print("WRITER RESULT:", result, flush=True)
'''

print()
print("1. BASELINE AUDIT:")
print(json.loads(AUDIT_PATH.read_text(encoding="utf-8")))

print()
print("2. STARTING TWO AUDIT WRITERS...")

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

print("PROCESS 1:")
print(out1)

if err1:
    print("PROCESS 1 STDERR:")
    print(err1)

print("PROCESS 2:")
print(out2)

if err2:
    print("PROCESS 2 STDERR:")
    print(err2)

assert p1.returncode == 0
assert p2.returncode == 0

print()
print("3. FINAL AUDIT:")

final_audit = json.loads(
    AUDIT_PATH.read_text(encoding="utf-8")
)

print(json.dumps(final_audit, indent=2))

writer_events = [
    e
    for e in final_audit
    if e.get("result") == "concurrent-audit-writer"
]

print()
print("CONCURRENT WRITER EVENTS:", len(writer_events))

assert len(writer_events) == 2
assert len(final_audit) == 3

print()
print("RESULT: PASS")
print("Both concurrent audit writers completed.")
print("Both audit events were persisted.")
print("No writer overwrote the other writer's event.")
print("Audit locking and atomic persistence work together safely.")
