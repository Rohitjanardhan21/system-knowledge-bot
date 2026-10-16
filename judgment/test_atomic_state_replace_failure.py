import json
from unittest.mock import patch

from judgment import recovery


def test_atomic_state_replace_failure_preserves_durable_state(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"

    original = {
        "actions": [{
            "action": "free-disk-space",
            "status": "executing",
            "execution_result": None,
        }]
    }
    state_path.write_text(json.dumps(original, indent=2), encoding="utf-8")

    monkeypatch.setattr(recovery, "STATE_PATH", state_path)

    candidate = json.loads(state_path.read_text(encoding="utf-8"))
    candidate["actions"][0]["status"] = "executed"
    candidate["actions"][0]["execution_result"] = "simulated-success"

    original_bytes = state_path.read_bytes()

    with patch(
        "judgment.recovery.os.replace",
        side_effect=RuntimeError("simulated-os-replace-failure"),
    ):
        try:
            recovery._atomic_write_state(candidate)
        except RuntimeError as exc:
            assert str(exc) == "simulated-os-replace-failure"
        else:
            raise AssertionError("Expected os.replace failure")

    # The authoritative file must remain byte-for-byte unchanged.
    assert state_path.read_bytes() == original_bytes

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    stored = persisted["actions"][0]
    assert stored["status"] == "executing"
    assert stored["execution_result"] is None

    # The current implementation writes the temp file before replacement.
    # On replacement failure it may remain; this test does not clean it up
    # implicitly or claim that cleanup is guaranteed.
    temp_path = state_path.with_suffix(".tmp")
    assert temp_path.exists()
    assert state_path.is_relative_to(tmp_path)
