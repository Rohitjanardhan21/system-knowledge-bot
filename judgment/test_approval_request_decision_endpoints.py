import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import backend.main as main


class ApprovalRequestDecisionEndpointTests(unittest.TestCase):
    def setUp(self):
        self.device_id = "approval-test-device"
        self.approval_id = "mock-approval-id"
        self.request_payload = main.ProcessApprovalRequestPayload(
            action="kill_high_cpu",
            pid=424242,
            create_time=1700000000.0,
            name="approval-test-no-real-process.exe",
            ttl_s=60.0,
        )
        self.decision_payload = main.ProcessApprovalDecisionPayload(
            approved=True
        )
        self.admin = {"scope": "admin", "sub": "test-admin-17"}

    def invoke_create(self, payload=None, principal=None, device_id=None):
        return asyncio.run(
            main.create_process_approval_request(
                device_id=device_id or self.device_id,
                payload=payload or self.request_payload,
                principal=principal or self.admin,
            )
        )

    def invoke_decision(self, payload=None, principal=None):
        return asyncio.run(
            main.decide_process_approval(
                approval_id=self.approval_id,
                payload=payload or self.decision_payload,
                principal=principal or self.admin,
            )
        )

    def test_create_records_authenticated_requester(self):
        expected = {
            "approval_id": self.approval_id,
            "status": "pending",
        }
        with (
            patch.object(main, "_devices", {self.device_id: {}}),
            patch(
                "backend.core.auth.approval_service.create_approval_request",
                return_value=expected,
            ) as create,
        ):
            result = self.invoke_create()

        self.assertEqual(result, expected)
        create.assert_called_once_with(
            requested_by="test-admin-17",
            device_id=self.device_id,
            action="kill_high_cpu",
            pid=424242,
            create_time=1700000000.0,
            name="approval-test-no-real-process.exe",
            ttl_s=60.0,
        )

    def test_unregistered_device_is_rejected(self):
        with (
            patch.object(main, "_devices", {}),
            patch(
                "backend.core.auth.approval_service.create_approval_request"
            ) as create,
        ):
            with self.assertRaises(HTTPException) as caught:
                self.invoke_create()

        self.assertEqual(caught.exception.status_code, 404)
        create.assert_not_called()

    def test_invalid_action_is_rejected(self):
        bad_payload = main.ProcessApprovalRequestPayload(
            action="arbitrary_command",
            pid=424242,
            create_time=1700000000.0,
            name="approval-test-no-real-process.exe",
        )
        with (
            patch.object(main, "_devices", {self.device_id: {}}),
            patch(
                "backend.core.auth.approval_service.create_approval_request",
                side_effect=ValueError("Action is not eligible"),
            ),
        ):
            with self.assertRaises(HTTPException) as caught:
                self.invoke_create(payload=bad_payload)

        self.assertEqual(caught.exception.status_code, 400)

    def test_create_service_failure_fails_closed(self):
        with (
            patch.object(main, "_devices", {self.device_id: {}}),
            patch(
                "backend.core.auth.approval_service.create_approval_request",
                side_effect=ConnectionError("simulated Redis outage"),
            ),
        ):
            with self.assertRaises(HTTPException) as caught:
                self.invoke_create()

        self.assertEqual(caught.exception.status_code, 503)

    def test_decision_records_authenticated_actor(self):
        with patch(
            "backend.core.auth.approval_service.decide_approval",
            return_value=True,
        ) as decide:
            result = self.invoke_decision()

        self.assertEqual(result["approval_id"], self.approval_id)
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["decided_by"], "test-admin-17")
        decide.assert_called_once_with(
            self.approval_id,
            approved=True,
            decided_by="test-admin-17",
        )

    def test_missing_or_already_decided_request_is_rejected(self):
        with patch(
            "backend.core.auth.approval_service.decide_approval",
            return_value=False,
        ):
            with self.assertRaises(HTTPException) as caught:
                self.invoke_decision()

        self.assertEqual(caught.exception.status_code, 409)

    def test_decision_service_failure_fails_closed(self):
        with patch(
            "backend.core.auth.approval_service.decide_approval",
            side_effect=ConnectionError("simulated Redis outage"),
        ):
            with self.assertRaises(HTTPException) as caught:
                self.invoke_decision()

        self.assertEqual(caught.exception.status_code, 503)

    def test_missing_actor_identity_is_rejected(self):
        with patch(
            "backend.core.auth.approval_service.decide_approval"
        ) as decide:
            with self.assertRaises(HTTPException) as caught:
                self.invoke_decision(principal={"scope": "admin"})

        self.assertEqual(caught.exception.status_code, 403)
        decide.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
