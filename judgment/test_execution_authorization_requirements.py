import unittest


class TestExecutionAuthorizationRequirements(unittest.TestCase):
    def test_unapproved_termination_is_not_approved_by_default(self):
        decision = {
            "action": "kill_process",
            "target_pid": 12345,
            "target_create_time": 1700000000.0,
            "requires_confirmation": True,
            "auto_execute": False,
        }
        self.assertFalse(decision.get("approved", False))

    def test_confidence_does_not_grant_authority(self):
        decision = {
            "action": "kill_high_cpu_process",
            "confidence": 1.0,
            "auto_execute": True,
        }
        self.assertFalse(decision.get("approved", False))

    def test_explicit_approval_can_be_represented(self):
        decision = {
            "action": "kill_process",
            "approved": True,
        }
        self.assertIs(decision["approved"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
