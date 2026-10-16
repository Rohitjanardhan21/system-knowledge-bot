import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.core.devices import command_service


AGENT_SCRIPT = Path(__file__).resolve().parents[1] / "agent.py"
AGENT_SPEC = importlib.util.spec_from_file_location(
    "cvis_device_agent_drop_caches_disabled_test",
    AGENT_SCRIPT,
)
if AGENT_SPEC is None or AGENT_SPEC.loader is None:
    raise ImportError(f"Unable to load device agent from {AGENT_SCRIPT}")

agent = importlib.util.module_from_spec(AGENT_SPEC)
AGENT_SPEC.loader.exec_module(agent)


def test_agent_blocks_drop_caches_before_os_side_effects():
    context = {
        "server": "https://example.invalid",
        "api_key": "test-key",
        "device_id": "test-device",
    }

    import subprocess

    with (
        patch.object(subprocess, "run") as run_mock,
        patch("builtins.open") as open_mock,
    ):
        result = agent.execute_device_command(
            "drop_caches",
            {"confirm": True, "cache_level": "3"},
            authorization_context=context,
        )

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "trusted_approval_not_implemented"
    run_mock.assert_not_called()
    open_mock.assert_not_called()


def test_drop_caches_is_not_in_server_allowlist():
    assert "drop_caches" not in command_service.ALLOWED_COMMANDS
    assert "clear_temp" in command_service.ALLOWED_COMMANDS


def test_command_service_rejects_drop_caches_creation():
    class FakeRedis:
        def __getattr__(self, name):
            pytest.fail(f"Redis must not be accessed: {name}")

    with pytest.raises(ValueError, match="Unsupported command type"):
        asyncio.run(
            command_service.create_command(
                FakeRedis(),
                device_id="test-device",
                command_type="drop_caches",
                requested_by="test-admin",
                payload={"confirm": True},
                ttl_s=60,
            )
        )


def test_agent_blocks_remote_clear_logs_before_file_operations():
    payload = {"paths": ["C:/important-data/do-not-delete.txt"]}
    context = {
        "server": "https://example.invalid",
        "api_key": "test-key",
        "device_id": "test-device",
    }

    with (
        patch.object(agent.os, "remove") as remove_mock,
        patch("builtins.open") as open_mock,
    ):
        result = agent.execute_device_command(
            "clear_logs",
            payload,
            authorization_context=context,
        )

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "trusted_log_path_policy_not_implemented"
    remove_mock.assert_not_called()
    open_mock.assert_not_called()


def test_clear_logs_is_not_in_server_allowlist():
    assert "clear_logs" not in command_service.ALLOWED_COMMANDS
    assert "clear_temp" in command_service.ALLOWED_COMMANDS


def test_command_service_rejects_clear_logs_creation():
    class FakeRedis:
        def __getattr__(self, name):
            pytest.fail(f"Redis must not be accessed: {name}")

    with pytest.raises(ValueError, match="Unsupported command type"):
        asyncio.run(
            command_service.create_command(
                FakeRedis(),
                device_id="test-device",
                command_type="clear_logs",
                requested_by="test-admin",
                payload={"paths": ["C:/important-data/do-not-delete.txt"]},
                ttl_s=60,
            )
        )
