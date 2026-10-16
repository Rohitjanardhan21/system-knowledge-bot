import time
import unittest
import redis

from backend.core.auth.approval_service import (
    create_approval_request,
    decide_approval,
    consume_approval,
)


class RealRedisApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = redis.Redis.from_url(
            __import__("os").environ.get(
                "REDIS_URL", "redis://localhost:6379/0"
            ),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        cls.client.ping()

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_real_redis_approval_lifecycle(self):
        request = create_approval_request(
            requested_by="approval-test-requester",
            device_id="approval-test-device",
            action="kill_process",
            pid=2147483000,
            create_time=time.time(),
            name="approval-test-no-real-process.exe",
            ttl_s=30,
            client=self.client,
        )
        approval_id = request["approval_id"]
        try:

            self.assertEqual(request["status"], "pending")
            self.assertTrue(
                decide_approval(
                    approval_id,
                    approved=True,
                    decided_by="approval-test-reviewer",
                    client=self.client,
                )
            )

            # A mismatched identity must not consume the approval.
            self.assertFalse(
                consume_approval(
                    approval_id,
                    device_id="approval-test-device",
                    action="kill_process",
                    pid=2147483000,
                    create_time=request["create_time"],
                    name="different-process.exe",
                    client=self.client,
                )
            )

            # The exact identity may consume it once.
            self.assertTrue(
                consume_approval(
                    approval_id,
                    device_id="approval-test-device",
                    action="kill_process",
                    pid=2147483000,
                    create_time=request["create_time"],
                    name="approval-test-no-real-process.exe",
                    client=self.client,
                )
            )

            # A second consumption must be denied.
            self.assertFalse(
                consume_approval(
                    approval_id,
                    device_id="approval-test-device",
                    action="kill_process",
                    pid=2147483000,
                    create_time=request["create_time"],
                    name="approval-test-no-real-process.exe",
                    client=self.client,
                )
            )

            print("PASS: pending -> approved -> consumed exactly once")
            print("PASS: mismatched process identity was denied")
            print("PASS: replay was denied")
        finally:
            self.client.delete(f"process:approval:{approval_id}")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        RealRedisApprovalTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
