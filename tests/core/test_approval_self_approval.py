import pytest

from backend.core.auth.approval_service import (
    SelfApprovalError,
    decide_approval,
)


class SelfApprovalRedisStub:
    def eval(self, script, key_count, key, *args):
        assert "requested_by == ARGV[3]" in script
        assert key_count == 1
        assert key
        assert args[1:] == ("approved", "requester")
        return -1


def test_requester_cannot_approve_own_request():
    with pytest.raises(SelfApprovalError):
        decide_approval(
            "approval-id",
            approved=True,
            decided_by="requester",
            client=SelfApprovalRedisStub(),
        )
