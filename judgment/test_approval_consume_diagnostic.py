import os
import time
import unittest
import redis

from backend.core.auth.approval_service import (
    create_approval_request,
    decide_approval,
    consume_approval,
)


class ApprovalConsumeDiagnostic(unittest.TestCase):
    def test_fresh_approval_consumption(self):
        client = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()

        try:
            pid = 2147482999
            create_time = time.time()
            name = "approval-diagnostic-no-real-process.exe"

            request = create_approval_request(
                requested_by="diagnostic-requester",
                device_id="diagnostic-device",
                action="kill_process",
                pid=pid,
                create_time=create_time,
                name=name,
                ttl_s=30,
                client=client,
            )

            self.assertTrue(
                decide_approval(
                    request["approval_id"],
                    approved=True,
                    decided_by="diagnostic-reviewer",
                    client=client,
                )
            )

            try:
                consumed = consume_approval(
                    request["approval_id"],
                    device_id="diagnostic-device",
                    action="kill_process",
                    pid=pid,
                    create_time=create_time,
                    name=name,
                    client=client,
                )
            except Exception as exc:
                print("CONSUME EXCEPTION:", type(exc).__name__, repr(str(exc)))
                raise

            print("CONSUME RESULT:", consumed)
            self.assertTrue(consumed)
        finally:
            client.close()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        ApprovalConsumeDiagnostic
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
