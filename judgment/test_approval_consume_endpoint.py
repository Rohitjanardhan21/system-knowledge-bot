import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.main import (
    ProcessApprovalConsumePayload,
    consume_process_approval,
)


class ApprovalConsumeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.payload = ProcessApprovalConsumePayload(
            action="kill_high_cpu",
            pid=2147483000,
            create_time=1700000000.0,
            name="approval-test-no-real-process.exe",
        )
        self.principal = {"scope": "write", "device_id": "device-A"}

    def invoke(self, device_id="device-A", principal=None):
        return asyncio.run(
            consume_process_approval(
                device_id=device_id,
                approval_id="test-approval-id",
                payload=self.payload,
                principal=principal or self.principal,
            )
        )

    def test_wrong_device_is_denied_before_consumption(self):
        with patch(
            "backend.core.auth.approval_service.consume_approval"
        ) as consume:
            with self.assertRaises(HTTPException) as caught:
                self.invoke(device_id="device-B")

        self.assertEqual(caught.exception.status_code, 403)
        consume.assert_not_called()

    def test_unbound_credential_is_denied(self):
        with patch(
            "backend.core.auth.approval_service.consume_approval"
        ) as consume:
            with self.assertRaises(HTTPException) as caught:
                self.invoke(principal={"scope": "write"})

        self.assertEqual(caught.exception.status_code, 403)
        consume.assert_not_called()

    def test_valid_approval_is_accepted(self):
        with patch(
            "backend.core.auth.approval_service.consume_approval",
            return_value=True,
        ) as consume:
            result = self.invoke()

        self.assertEqual(result, {"authorized": True})
        consume.assert_called_once_with(
            "test-approval-id",
            device_id="device-A",
            action="kill_high_cpu",
            pid=2147483000,
            create_time=1700000000.0,
            name="approval-test-no-real-process.exe",
        )

    def test_invalid_or_replayed_approval_is_denied(self):
        with patch(
            "backend.core.auth.approval_service.consume_approval",
            return_value=False,
        ):
            with self.assertRaises(HTTPException) as caught:
                self.invoke()

        self.assertEqual(caught.exception.status_code, 409)

    def test_approval_service_failure_fails_closed(self):
        with patch(
            "backend.core.auth.approval_service.consume_approval",
            side_effect=ConnectionError("simulated Redis outage"),
        ):
            with self.assertRaises(HTTPException) as caught:
                self.invoke()

        self.assertEqual(caught.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
