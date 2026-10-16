from backend.core.actions.action_executor import AUTONOMOUS_ALLOWED_ACTIONS
from backend.core.actions.auto_remediation import AutoRemediationEngine


def test_every_mapped_automatic_action_is_allowlisted():
    mapped_actions = {
        action["action_id"]
        for actions in AutoRemediationEngine.REMEDIATION_MAP.values()
        for action in actions
    }

    assert mapped_actions <= AUTONOMOUS_ALLOWED_ACTIONS


def test_disk_full_only_maps_to_clear_temp():
    actions = AutoRemediationEngine.REMEDIATION_MAP["DISK_FULL"]

    assert [action["action_id"] for action in actions] == ["clear_temp"]


def test_oom_has_no_automatic_remediation():
    assert AutoRemediationEngine.REMEDIATION_MAP["OOM"] == []
