import unittest
from unittest.mock import MagicMock, patch

from backend.core.auth import approval_service as svc


class ApprovalServiceBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.redis = MagicMock()
        self.redis.eval.return_value = 1

    def test_request_is_pending_and_identity_bound(self):
        with patch.object(svc.time, "time", return_value=100.0):
            result = svc.create_approval_request(
                requested_by="admin-1", device_id="device-1",
                action="kill_high_cpu", pid=1234, create_time=100.5,
                name="example.exe", ttl_s=60, client=self.redis,
            )
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["device_id"], "device-1")
        self.assertEqual(result["action"], "kill_high_cpu")
        self.assertEqual(result["pid"], 1234)
        self.assertEqual(result["create_time"], 100.5)
        self.assertEqual(result["name"], "example.exe")
        self.assertTrue(result["approval_id"])
        self.redis.pipeline.assert_called_once()

    def test_invalid_ttl_is_rejected(self):
        with self.assertRaises(ValueError):
            svc.create_approval_request(
                requested_by="admin-1", device_id="device-1",
                action="kill_high_cpu", pid=1234, create_time=100.5,
                name="example.exe", ttl_s=121, client=self.redis,
            )

    def test_approval_decision_uses_atomic_redis_script(self):
        with patch.object(svc.time, "time", return_value=100.0):
            result = svc.decide_approval(
                "opaque-id", approved=True, decided_by="admin-1",
                client=self.redis,
            )
        self.assertTrue(result)
        args = self.redis.eval.call_args.args
        self.assertEqual(args[1], 1)
        self.assertEqual(args[2], "process:approval:opaque-id")
        self.assertEqual(args[4], "approved")

    def test_rejection_is_a_distinct_decision(self):
        svc.decide_approval(
            "opaque-id", approved=False, decided_by="admin-1",
            client=self.redis,
        )
        self.assertEqual(self.redis.eval.call_args.args[4], "rejected")

    def test_consumption_is_bound_to_exact_identity(self):
        svc.consume_approval(
            "opaque-id", device_id="device-1", action="kill_high_cpu",
            pid=1234, create_time=100.5, name="example.exe",
            client=self.redis,
        )
        args = self.redis.eval.call_args.args
        self.assertEqual(args[2], "process:approval:opaque-id")
        self.assertEqual(args[4:], (
            "device-1", "kill_high_cpu", "1234",
            format(100.5, ".17g"), "example.exe",
        ))

    def test_failed_atomic_consumption_is_denied(self):
        self.redis.eval.return_value = 0
        result = svc.consume_approval(
            "opaque-id", device_id="device-1", action="kill_high_cpu",
            pid=1234, create_time=100.5, name="example.exe",
            client=self.redis,
        )
        self.assertFalse(result)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        ApprovalServiceBehaviorTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
