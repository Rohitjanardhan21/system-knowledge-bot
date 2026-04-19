from agent.agent_core import handle_question

# Fake minimal facts
FACTS = {
    "metadata": {
        "collected_at": "2026-01-20T10:00:00",
        "ttl_seconds": 300
    },
    "posture": {"posture": "idle-capable"},
    "cpu": {},
    "memory": {},
    "history": {}
}

def test(q):
    r = handle_question(q, FACTS)
    print(f"\nQ: {q}")
    print(f"MODE: {r.mode}")
    print(f"TEXT: {r.text}")
    print(f"VISUAL: {r.visual}")

test("is my system healthy")
test("show me today")
test("predict crash tomorrow")
test("can i run another job")
