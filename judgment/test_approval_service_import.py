"""Import/syntax smoke test for the approval service."""
import unittest

from backend.core.auth import approval_service


class ApprovalServiceImportTests(unittest.TestCase):
    def test_process_actions_are_explicitly_allowlisted(self):
        self.assertEqual(
            approval_service.ALLOWED_ACTIONS,
            frozenset({
                "kill_high_cpu",
                "kill_process",
                "kill_high_cpu_process",
            }),
        )

    def test_approval_lifetime_is_bounded(self):
        self.assertEqual(approval_service.MAX_APPROVAL_TTL_S, 120.0)

    def test_identity_rejects_missing_device(self):
        with self.assertRaises(ValueError):
            approval_service._identity(
                "", "kill_high_cpu", 1234, 100.5, "example.exe"
            )

    def test_identity_rejects_invalid_pid(self):
        with self.assertRaises(ValueError):
            approval_service._identity(
                "device-1", "kill_high_cpu", 0, 100.5, "example.exe"
            )

    def test_identity_rejects_non_allowlisted_action(self):
        with self.assertRaises(ValueError):
            approval_service._identity(
                "device-1", "clear_temp", 1234, 100.5, "example.exe"
            )


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        ApprovalServiceImportTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
