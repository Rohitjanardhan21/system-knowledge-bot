from pathlib import Path


def test_command_dispatch_sources_keep_explicit_safety_guards():
    repository_root = Path(__file__).resolve().parents[1]
    service_source = (
        repository_root / "backend" / "core" / "devices" / "command_service.py"
    ).read_text(encoding="utf-8-sig", errors="replace")
    agent_source = (repository_root / "agent.py").read_text(
        encoding="utf-8-sig",
        errors="replace",
    )

    assert "ALLOWED_COMMANDS" in service_source
    assert "trusted_approval_not_implemented" in agent_source
    assert "trusted_log_path_policy_not_implemented" in agent_source
