import unittest
from unittest.mock import Mock, patch

from backend.action_executor import ActionExecutor


class ApprovalGateFailureTests(unittest.TestCase):
    def setUp(self):
        self.executor = ActionExecutor.__new__(ActionExecutor)
        self.executor.agent = Mock()
        self.executor.agent.encode_state.return_value = [0]
        self.executor.simulator = Mock()
        self.executor.simulator.apply_action.return_value = {}
        self.executor.simulator.evaluate_state.return_value = 0

    def run_action(self, action, approval_id=None, consume_side_effect=None):
        decision = {
            "action": action,
            "context": "general",
            "target_name": "approval-test-no-real-process.exe",
            "target_pid": 2147483000,
            "target_create_time": 1700000000.0,
            "baseline_cpu": 0,
            "duration_seconds": 30,
            "device_id": "approval-test-device",
        }
        if approval_id is not None:
            decision["approval_id"] = approval_id

        with patch.object(
            self.executor, "get_metrics",
            return_value={"cpu": 100, "memory": 20, "disk": 20}
        ), patch(
            "backend.action_executor.CausalEngine"
        ) as causal, patch(
            "backend.action_executor.is_action_allowed",
            return_value=(True, "allowed")
        ), patch(
            "backend.action_executor.is_safe", return_value=True
        ), patch.object(
            self.executor, "can_execute", return_value=True
        ), patch(
            "backend.action_executor.get_optimizer",
            return_value={"reward_scale": 1.0}
        ), patch.object(
            self.executor, "_execute_action"
        ) as dispatch, patch(
            "backend.core.auth.approval_service.consume_approval",
            return_value=False,
            side_effect=consume_side_effect,
        ) as consume:
            causal.return_value.detect.return_value = {
                "primary_cause": {
                    "process": "approval-test-no-real-process.exe",
                    "contributors": [],
                }
            }

            result = self.executor.execute(decision, source="manual")

        dispatch.assert_not_called()
        return result, consume

    def test_missing_approval_is_blocked(self):
        for action in ("kill_process", "kill_high_cpu_process"):
            with self.subTest(action=action):
                result, consume = self.run_action(action)
                self.assertEqual(result["status"], "blocked_approval")
                consume.assert_not_called()

    def test_invalid_or_replayed_approval_is_blocked(self):
        for action in ("kill_process", "kill_high_cpu_process"):
            with self.subTest(action=action):
                result, consume = self.run_action(
                    action, approval_id="invalid-or-replayed-test-id"
                )
                self.assertEqual(result["status"], "blocked_approval")
                self.assertEqual(
                    result["reason"],
                    "approval_invalid_expired_or_already_used",
                )
                consume.assert_called_once()

    def test_redis_error_fails_closed(self):
        for action in ("kill_process", "kill_high_cpu_process"):
            with self.subTest(action=action):
                result, _ = self.run_action(
                    action,
                    approval_id="redis-outage-test-id",
                    consume_side_effect=ConnectionError("test Redis outage"),
                )

                self.assertEqual(result["status"], "blocked_approval")
                self.assertEqual(
                    result["reason"],
                    "approval_verification_unavailable",
                )


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        ApprovalGateFailureTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
