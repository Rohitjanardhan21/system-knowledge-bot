import unittest


class ApprovalContractTests(unittest.TestCase):
    def test_process_termination_requires_explicit_approval(self):
        self.assertFalse(
            self.approved(
                approval=None,
                action="kill_high_cpu",
                pid=1234,
                create_time=100.5,
                name="example.exe",
            )
        )

    def test_confidence_does_not_grant_authority(self):
        self.assertFalse(
            self.approved(
                approval=None,
                action="kill_high_cpu",
                pid=1234,
                create_time=100.5,
                name="example.exe",
                confidence=1.0,
            )
        )

    def test_approval_must_match_exact_process_identity(self):
        approval = self.record()
        self.assertFalse(
            self.approved(
                approval=approval,
                action="kill_high_cpu",
                pid=1234,
                create_time=100.6,
                name="example.exe",
            )
        )

    def test_expired_approval_is_rejected(self):
        approval = self.record(expires_at=99.0)
        self.assertFalse(
            self.approved(
                approval=approval,
                action="kill_high_cpu",
                pid=1234,
                create_time=100.5,
                name="example.exe",
                now=100.0,
            )
        )

    def test_approval_cannot_be_reused(self):
        approval = self.record()
        self.assertTrue(
            self.approved(
                approval=approval,
                action="kill_high_cpu",
                pid=1234,
                create_time=100.5,
                name="example.exe",
            )
        )
        approval["consumed"] = True
        self.assertFalse(
            self.approved(
                approval=approval,
                action="kill_high_cpu",
                pid=1234,
                create_time=100.5,
                name="example.exe",
            )
        )

    @staticmethod
    def record(expires_at=200.0):
        return {
            "approved": True,
            "action": "kill_high_cpu",
            "pid": 1234,
            "create_time": 100.5,
            "name": "example.exe",
            "expires_at": expires_at,
            "consumed": False,
        }

    @staticmethod
    def approved(
        approval,
        action,
        pid,
        create_time,
        name,
        now=100.0,
        confidence=0.0,
    ):
        if not isinstance(approval, dict):
            return False
        return (
            approval.get("approved") is True
            and approval.get("consumed") is False
            and approval.get("action") == action
            and approval.get("pid") == pid
            and approval.get("create_time") == create_time
            and approval.get("name") == name
            and isinstance(approval.get("expires_at"), (int, float))
            and approval["expires_at"] > now
        )


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        ApprovalContractTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
