from agent.agent_core import handle_question


FACTS = {
    "metadata": {
        "collected_at": "2026-01-20T10:00:00+00:00",
        "ttl_seconds": 300,
    },
    "posture": {"posture": "idle-capable"},
    "cpu": {},
    "memory": {},
    "history": {},
}


def assert_agent_response(response):
    assert isinstance(response, dict)
    assert "mode" in response
    assert "text" in response
    assert "visual" in response
    assert "confidence" in response
    assert "evidence" in response
    assert "reason" in response


def test_system_health_question():
    response = handle_question("is my system healthy", FACTS)
    assert_agent_response(response)


def test_today_question():
    response = handle_question("show me today", FACTS)
    assert_agent_response(response)


def test_prediction_question():
    response = handle_question("predict crash tomorrow", FACTS)
    assert_agent_response(response)


def test_job_question():
    response = handle_question("can i run another job", FACTS)
    assert_agent_response(response)
