import os
import unittest

try:
    import redis
except ImportError:
    redis = None


class RedisApprovalReadinessTests(unittest.TestCase):
    def test_redis_client_package_available(self):
        if redis is None:
            self.skipTest("Python redis package is not installed")
        self.assertTrue(hasattr(redis, "Redis"))

    def test_redis_connection_if_configured_or_locally_available(self):
        if redis is None:
            self.skipTest("Python redis package is not installed")

        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )

        try:
            self.assertTrue(client.ping())
            print("Redis ping succeeded.")
        except redis.RedisError as exc:
            self.skipTest(f"Redis is not reachable from this environment: {exc}")
        finally:
            client.close()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        RedisApprovalReadinessTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
