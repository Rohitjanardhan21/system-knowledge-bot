import importlib.util
from pathlib import Path
import subprocess
from unittest.mock import mock_open, patch


AGENT_SCRIPT = Path(__file__).resolve().parents[2] / "agent.py"
AGENT_SPEC = importlib.util.spec_from_file_location(
    "cvis_device_agent_drop_caches_test",
    AGENT_SCRIPT,
)
if AGENT_SPEC is None or AGENT_SPEC.loader is None:
    raise ImportError(f"Unable to load device agent from {AGENT_SCRIPT}")

agent = importlib.util.module_from_spec(AGENT_SPEC)
AGENT_SPEC.loader.exec_module(agent)


def test_drop_caches_confirmation_without_device_context_is_denied():
    with (
        patch.object(agent, "OS", "Linux"),
        patch.object(agent.os, "geteuid", return_value=0, create=True),
        patch.object(subprocess, "run") as run,
        patch("builtins.open", mock_open()) as open_file,
    ):
        result = agent.execute_device_command(
            "drop_caches",
            {"confirm": True},
        )

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "trusted_approval_not_implemented"
    run.assert_not_called()
    open_file.assert_not_called()


def test_drop_caches_remains_disabled_with_device_context():
    authorized_context = {
        "server": "http://127.0.0.1:8000",
        "api_key": "test-device-key",
        "device_id": "test-device",
    }

    with (
        patch.object(agent, "OS", "Linux"),
        patch.object(agent.os, "geteuid", return_value=0, create=True),
        patch.object(subprocess, "run") as run,
        patch("builtins.open") as open_file,
    ):
        result = agent.execute_device_command(
            "drop_caches",
            {"confirm": True, "cache_level": "3"},
            authorization_context=authorized_context,
        )

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "trusted_approval_not_implemented"
    run.assert_not_called()
    open_file.assert_not_called()


def test_cache_cleanup_requires_explicit_confirmation():
    with patch.object(subprocess, "run") as run:
        for command in ("clear_pip_cache", "clear_docker_cache"):
            result = agent.execute_device_command(
                command,
                {},
                authorization_context={
                    "server": "http://127.0.0.1:8000",
                    "api_key": "test-device-key",
                    "device_id": "test-device",
                },
            )

            assert result["success"] is False
            assert result["blocked"] is True
            assert result["reason"] == "explicit_confirmation_required"
        run.assert_not_called()


def test_cache_cleanup_requires_authenticated_device_context():
    with patch.object(subprocess, "run") as run:
            for command in ("clear_pip_cache", "clear_docker_cache"):
                result = agent.execute_device_command(
                    command,
                    {"confirm": True},
                )

                assert result["success"] is False
                assert result["blocked"] is True
                assert result["reason"] == "authenticated_device_command_required"
            run.assert_not_called()
