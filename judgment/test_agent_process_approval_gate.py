import importlib.util
from pathlib import Path
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


AGENT_SCRIPT = Path(__file__).resolve().parents[1] / "agent.py"
agent: ModuleType


class AgentProcessApprovalGateTests(unittest.TestCase):
    PID = 424242
    CREATE_TIME = 1700000000.0
    NAME = "approval-test-no-real-process.exe"

    @classmethod
    def setUpClass(cls):
        global agent
        spec = importlib.util.spec_from_file_location(
            "cvis_device_agent",
            AGENT_SCRIPT,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load device agent from {AGENT_SCRIPT}")

        agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent)

    def setUp(self):
        self.proc = Mock()
        self.proc.pid = self.PID
        self.proc.name.return_value = self.NAME
        self.proc.create_time.return_value = self.CREATE_TIME
        self.proc.as_dict.return_value = {
            "pid": self.PID,
            "name": self.NAME,
            "create_time": self.CREATE_TIME,
            "username": "test-user",
            "cmdline": ["mock-process"],
        }
        self.proc.cpu_percent.return_value = 80.0
        self.proc.memory_percent.return_value = 15.0
        self.proc.wait.return_value = None

        self.payload = {
            "pid": self.PID,
            "create_time": self.CREATE_TIME,
            "name": self.NAME,
            "confirm": True,
            "approval_id": "mock-approval-id",
        }
        self.context = {
            "server": "http://127.0.0.1:8000",
            "api_key": "test-key-not-real",
            "device_id": "test-device",
        }

        self.ps_ok = patch.object(agent, "PS_OK", True)
        self.ps_ok.start()
        self.addCleanup(self.ps_ok.stop)

        self.process_patch = patch.object(
            agent.psutil, "Process", return_value=self.proc
        )
        self.process_patch.start()
        self.addCleanup(self.process_patch.stop)

        self.pid_patch = patch.object(agent.os, "getpid", return_value=999999)
        self.pid_patch.start()
        self.addCleanup(self.pid_patch.stop)

    def execute(self, context=None):
        return agent.execute_device_command(
            "kill_high_cpu",
            self.payload,
            authorization_context=context,
        )

    def test_denied_approval_never_terminates(self):
        with patch.object(
            agent, "consume_process_approval", return_value=False
        ) as consume:
            result = self.execute(self.context)

        self.assertFalse(result["success"])
        self.assertIn("approval", result["error"].lower())
        self.proc.terminate.assert_not_called()
        self.proc.wait.assert_not_called()
        consume.assert_called_once_with(
            self.context["server"],
            self.context["api_key"],
            self.context["device_id"],
            "mock-approval-id",
            "kill_high_cpu",
            self.PID,
            self.CREATE_TIME,
            self.NAME,
        )

    def test_missing_context_never_terminates(self):
        result = self.execute()

        self.assertFalse(result["success"])
        self.proc.terminate.assert_not_called()
        self.proc.wait.assert_not_called()

    def test_valid_approval_reaches_only_mocked_termination(self):
        with patch.object(
            agent, "consume_process_approval", return_value=True
        ) as consume:
            result = self.execute(self.context)

        self.assertTrue(result["success"])
        self.assertTrue(result["terminated"])
        self.proc.terminate.assert_called_once_with()
        self.proc.wait.assert_called_once_with(timeout=5)
        consume.assert_called_once()

    def test_approval_helper_fails_closed_on_network_error(self):
        with patch.object(
            agent.urllib.request,
            "urlopen",
            side_effect=agent.urllib.error.URLError("simulated outage"),
        ):
            authorized = agent.consume_process_approval(
                self.context["server"],
                self.context["api_key"],
                self.context["device_id"],
                "mock-approval-id",
                "kill_high_cpu",
                self.PID,
                self.CREATE_TIME,
                self.NAME,
            )

        self.assertIs(authorized, False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
