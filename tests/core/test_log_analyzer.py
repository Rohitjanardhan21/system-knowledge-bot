import json
from unittest.mock import patch

import pytest

from backend.core.diagnostics.log_analyzer import (
    MAX_INPUT_CHARS,
    analyze_log,
    analyze_with_local_model,
)


def test_cuda_error_report_includes_evidence_and_cautious_hypotheses():
    content = (
        "2026-10-24T10:00:00Z ERROR RuntimeError: CUDA error: "
        "device-side assert triggered\n"
        "  at train_step (trainer.py:42)\n"
    )

    report = analyze_log(content, "training.log")

    cuda = next(finding for finding in report["findings"] if finding["category"] == "ai_ml")
    assert "device-side assert" in cuda["evidence"][0]
    assert any("indices" in hypothesis for hypothesis in cuda["hypotheses"])
    assert report["summary"]["timestamp_count"] == 1
    assert report["summary"]["stack_frame_count"] == 1
    assert report["input_format"] == "text"


def test_unfamiliar_exception_requests_context_without_claiming_a_cause():
    report = analyze_log("CustomStateError: inconsistent state")

    unknown = next(finding for finding in report["findings"] if finding["category"] == "unknown")
    assert unknown["confidence"] < 30
    assert "cannot identify" in unknown["summary"].lower()
    assert any("20–30 log lines" in check for check in unknown["troubleshooting"])


def test_json_report_extracts_severity_code_and_service():
    content = json.dumps({
        "timestamp": "2026-10-24T10:00:00Z",
        "severity": "ERROR",
        "service": "redis",
        "message": "Redis connection refused",
        "code": "ECONNREFUSED",
    })

    report = analyze_log(content, "incident.json")

    assert report["input_format"] == "json"
    assert report["summary"]["error_count"] >= 1
    assert [service.casefold() for service in report["summary"]["services"]] == ["redis"]
    assert any(finding["category"] == "networking" for finding in report["findings"])


def test_pasted_jsonl_is_normalized_as_structured_records():
    content = (
        '{"timestamp":"2026-10-24T10:00:00Z","severity":"ERROR",'
        '"message":"connection refused"}\n'
        '{"service":"api","message":"retry failed"}'
    )

    report = analyze_log(content)

    assert report["input_format"] == "jsonl"
    assert report["summary"]["error_count"] == 1
    assert any(finding["category"] == "networking" for finding in report["findings"])


def test_missing_yaml_module_recommends_the_python_distribution_and_verification():
    report = analyze_log("ModuleNotFoundError: No module named 'yaml'")

    package = report["findings"][0]
    assert package["category"] == "package_dependency"
    assert package["title"] == "Python dependency missing: PyYAML"
    assert any("python -m pip install PyYAML" in step for step in package["troubleshooting"])
    assert any("python -m pip show PyYAML" in step for step in package["troubleshooting"])
    assert any("dependency file" in step for step in package["troubleshooting"])
    assert any("Rerun the application" in step for step in package["verification"])


def test_cuda_hypotheses_are_gated_by_async_and_configuration_evidence():
    report = analyze_log("RuntimeError: CUDA error: device-side assert triggered")
    finding = next(item for item in report["findings"] if item["category"] == "ai_ml")

    assert not any("asynchronous" in item for item in finding["hypotheses"])
    assert not any("mismatch" in item or "memory pressure" in item for item in finding["hypotheses"])
    assert "not a calibrated probability" in finding["confidence_basis"]


def test_one_error_reports_insufficient_history_instead_of_nearby_correlation():
    report = analyze_log("2026-10-24T10:00:00Z ERROR CustomStateError: inconsistent state")

    assert report["correlation"]["status"] == "insufficient_history"
    assert "insufficient event history" in report["correlation"]["message"]
    assert not any(item["category"] == "event_correlation" for item in report["findings"])


def test_shared_request_id_supports_a_cautious_database_to_api_hypothesis():
    content = (
        '{"timestamp":"2026-10-24T10:00:00Z","severity":"ERROR",'
        '"service":"postgres","request_id":"req-100",'
        '"message":"connection refused at 127.0.0.1:5432"}\n'
        '{"timestamp":"2026-10-24T10:00:02Z","severity":"ERROR",'
        '"service":"api","request_id":"req-100","message":"HTTP 503 Service Unavailable"}'
    )

    report = analyze_log(content)
    correlation = report["findings"][0]

    assert correlation["category"] == "event_correlation"
    assert "Leading hypothesis" in correlation["summary"]
    assert "do not prove causation" in correlation["summary"]
    assert "127.0.0.1:5432" in "\n".join(correlation["evidence"])
    assert "req-100" in "\n".join(correlation["troubleshooting"])


def test_shared_request_id_ranks_database_health_check_and_503_chain_first():
    content = (
        '{"timestamp":"2026-10-24T10:00:00Z","severity":"ERROR",'
        '"service":"postgres","request_id":"req-100",'
        '"message":"connection refused at 127.0.0.1:5432"}\n'
        '{"timestamp":"2026-10-24T10:00:01Z","severity":"ERROR",'
        '"service":"api","request_id":"req-100",'
        '"message":"Database health check failed"}\n'
        '{"timestamp":"2026-10-24T10:00:02Z","severity":"ERROR",'
        '"service":"api","request_id":"req-100",'
        '"message":"HTTP 503 Service Unavailable"}'
    )

    report = analyze_log(content)
    finding = report["findings"][0]

    assert finding["category"] == "event_correlation"
    assert finding["title"].startswith("Database failure may explain")
    assert len(finding["evidence"]) == 3
    assert ["postgres", "api", "api"] == [
        event["service"] for event in report["events"]
    ]
    assert "req-100" in finding["summary"]
    assert "not confirmed causation" in finding["summary"]
    assert any("PostgreSQL" in step for step in finding["troubleshooting"])
    assert any("health-check logs" in step for step in finding["troubleshooting"])
    assert len(report["findings"]) == 1


def test_database_health_chain_rejects_out_of_order_events():
    content = (
        '{"timestamp":"2026-10-24T10:00:00Z","severity":"ERROR",'
        '"service":"api","request_id":"req-100",'
        '"message":"HTTP 503 Service Unavailable"}\n'
        '{"timestamp":"2026-10-24T10:00:01Z","severity":"ERROR",'
        '"service":"api","request_id":"req-100",'
        '"message":"Database health check failed"}\n'
        '{"timestamp":"2026-10-24T10:00:02Z","severity":"ERROR",'
        '"service":"postgres","request_id":"req-100",'
        '"message":"connection refused"}'
    )

    report = analyze_log(content)

    assert not any(
        item["title"].startswith("Database failure may explain")
        for item in report["findings"]
    )


def test_database_health_chain_requires_all_three_events_and_shared_request_id():
    content = (
        '{"timestamp":"2026-10-24T10:00:00Z","severity":"ERROR",'
        '"service":"postgres","request_id":"req-100",'
        '"message":"connection refused"}\n'
        '{"timestamp":"2026-10-24T10:00:01Z","severity":"ERROR",'
        '"service":"api","request_id":"req-200",'
        '"message":"Database health check failed"}\n'
        '{"timestamp":"2026-10-24T10:00:02Z","severity":"ERROR",'
        '"service":"api","request_id":"req-100",'
        '"message":"HTTP 503 Service Unavailable"}'
    )

    report = analyze_log(content)

    assert not any(
        item["title"].startswith("Database failure may explain")
        for item in report["findings"]
    )


def test_dependency_and_api_errors_without_request_id_are_only_weakly_related():
    content = (
        '{"timestamp":"2026-10-24T10:00:00Z","severity":"ERROR",'
        '"service":"postgres","message":"connection refused"}\n'
        '{"timestamp":"2026-10-24T10:00:20Z","severity":"ERROR",'
        '"service":"api","message":"HTTP 503 Service Unavailable"}'
    )

    report = analyze_log(content)
    correlation = next(item for item in report["findings"] if item["category"] == "event_correlation")

    assert correlation["confidence"] < 50
    assert "potentially related or independent" in correlation["summary"]
    assert "shared request ID" in correlation["summary"]


def test_nearby_unrelated_errors_are_not_correlated_by_proximity_alone():
    content = (
        "2026-10-24T10:00:00Z ERROR service=worker CustomWorkerError: failed\n"
        "2026-10-24T10:00:01Z ERROR service=api HTTP 503 Service Unavailable"
    )

    report = analyze_log(content)

    assert report["correlation"]["status"] == "not_established"
    assert "proximity alone is insufficient" in report["correlation"]["message"]
    assert not any(item["category"] == "event_correlation" for item in report["findings"])


def test_unknown_status_requests_operation_worker_version_and_request_logs():
    report = analyze_log(
        "2026-10-24T10:00:00Z ERROR worker-2 status 7421 request_id=req-8f12"
    )
    unknown = next(item for item in report["findings"] if item["category"] == "unknown")

    assert any("worker's version" in step for step in unknown["troubleshooting"])
    assert any("status 7421" in step for step in unknown["troubleshooting"])
    assert any("req-8f12" in step for step in unknown["troubleshooting"])


def test_xml_junit_extracts_failure_records():
    content = (
        "<testsuite><testcase name='connect'>"
        "<failure message='connection refused'>Backend unavailable</failure>"
        "</testcase></testsuite>"
    )

    report = analyze_log(content, "results.xml")

    assert report["input_format"] == "xml"
    assert any("connection refused" in event["text"] for event in report["events"])
    assert any(finding["category"] == "networking" for finding in report["findings"])


def test_local_model_requires_explicit_configuration(monkeypatch):
    monkeypatch.delenv("CVIS_LOCAL_LLM_MODEL", raising=False)

    report = analyze_log("unknown")

    assert report["local_model_configured"] is False
    with pytest.raises(ValueError, match="model name"):
        analyze_with_local_model("private log", "")


def test_local_model_evidence_quotes_are_validated_and_confidence_is_capped():
    content = "RuntimeError: CUDA error: device-side assert triggered"
    model_result = {
        "response": json.dumps({
            "hypotheses": [{
                "hypothesis": "An invalid tensor index may be involved.",
                "evidence_quotes": [content, "invented log evidence"],
                "confidence": "high",
                "alternatives": ["An earlier asynchronous operation may be involved."],
                "checks": ["Check index bounds."],
            }],
            "missing_context": [],
        })
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps(model_result).encode()

    with patch(
        "backend.core.diagnostics.log_analyzer.urllib.request.urlopen",
        return_value=Response(),
    ) as urlopen:
        result = analyze_with_local_model(content, "local-test-model")

    assert result["hypotheses"][0]["evidence_quotes"] == [content]
    assert result["hypotheses"][0]["confidence"] == "low"
    request = urlopen.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/api/generate"
    assert content in json.loads(request.data)["prompt"]
    assert MAX_INPUT_CHARS > len(content)
