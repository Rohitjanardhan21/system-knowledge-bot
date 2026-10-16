import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.main as main
import backend.core.auth.auth as auth


class ApprovalHttpAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.device_id = "approval-http-test-device"
        self.request_body = {
            "action": "kill_high_cpu",
            "pid": 424242,
            "create_time": 1700000000.0,
            "name": "approval-test-no-real-process.exe",
            "ttl_s": 60.0,
        }
        self.decision_body = {"approved": True}

    def test_unauthenticated_request_creation_is_rejected(self):
        with patch.object(main, "_devices", {self.device_id: {}}):
            response = self.client.post(
                f"/devices/{self.device_id}/approvals",
                json=self.request_body,
            )

        self.assertEqual(response.status_code, 401, response.text)

    def test_write_scope_cannot_create_approval(self):
        async def verify_key(_key):
            return {"scope": "write", "name": "test-write-user"}

        with (
            patch.object(main, "_devices", {self.device_id: {}}),
            patch.object(auth, "_verify_api_key", new=verify_key),
            patch(
                "backend.core.auth.approval_service.create_approval_request"
            ) as create,
        ):
            response = self.client.post(
                f"/devices/{self.device_id}/approvals",
                headers={"X-API-Key": "mock-write-key"},
                json=self.request_body,
            )

        self.assertEqual(response.status_code, 403, response.text)
        create.assert_not_called()

    def test_unauthenticated_decision_is_rejected(self):
        response = self.client.post(
            "/approvals/mock-approval-id/decision",
            json=self.decision_body,
        )

        self.assertEqual(response.status_code, 401, response.text)

    def test_write_scope_cannot_decide_approval(self):
        async def verify_key(_key):
            return {"scope": "write", "name": "test-write-user"}

        with (
            patch.object(auth, "_verify_api_key", new=verify_key),
            patch(
                "backend.core.auth.approval_service.decide_approval"
            ) as decide,
        ):
            response = self.client.post(
                "/approvals/mock-approval-id/decision",
                headers={"X-API-Key": "mock-write-key"},
                json=self.decision_body,
            )

        self.assertEqual(response.status_code, 403, response.text)
        decide.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
