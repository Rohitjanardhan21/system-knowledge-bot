import time
import unittest

import redis

from backend.core.auth.approval_service import (
    _redis_client,
    create_approval_request,
    decide_approval,
    consume_approval,
)


class DefaultRedisClientTests(unittest.TestCase):
    def test_default_client_approval_flow(self):
        client = _redis_client()
        try:
            client.ping()
        except (
            redis.exceptions.ConnectionError,
            redis.exceptions.TimeoutError,
        ) as exc:
            client.close()
            self.skipTest(f"Configured Redis service is unavailable: {exc}")

        request = None
        try:
            request = create_approval_request(
                requested_by="default-client-test",
                device_id="default-client-test-device",
                action="kill_process",
                pid=2147482998,
                create_time=time.time(),
                name="default-client-no-real-process.exe",
                ttl_s=30,
                client=client,
            )

            self.assertTrue(
                decide_approval(
                    request["approval_id"],
                    approved=True,
                    decided_by="default-client-test-reviewer",
                    client=client,
                )
            )

            consumed = consume_approval(
                request["approval_id"],
                device_id="default-client-test-device",
                action="kill_process",
                pid=2147482998,
                create_time=request["create_time"],
                name="default-client-no-real-process.exe",
                client=client,
            )
            self.assertTrue(consumed)
            print("PASS: approval consumed using the service's default Redis client")
        finally:
            try:
                if request is not None:
                    client.delete(
                        f"process:approval:{request['approval_id']}"
                    )
            finally:
                client.close()



if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        DefaultRedisClientTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
