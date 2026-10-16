import json

from state import state_reader


def test_state_and_audit_are_readable_from_isolated_files(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    state_path = state_dir / "latest.json"
    audit_path = state_dir / "audit.json"

    expected_state = {
        "actions": [{
            "action": "free-disk-space",
            "status": "failed",
            "execution_result": "interrupted-by-restart",
        }]
    }
    expected_audit = [{
        "event": "recovery-interrupted",
        "action": "free-disk-space",
        "status": "failed",
        "result": "interrupted-by-restart",
    }]

    state_path.write_text(
        json.dumps(expected_state), encoding="utf-8"
    )
    audit_path.write_text(
        json.dumps(expected_audit), encoding="utf-8"
    )

    # Inspect the reader implementation before assuming its path configuration.
    monkeypatch.setattr(state_reader, "STATE_PATH", state_path, raising=False)
    monkeypatch.setattr(state_reader, "AUDIT_PATH", audit_path, raising=False)

    state = state_reader.load_latest_state()
    audit = state_reader.load_audit()

    assert isinstance(state, dict)
    assert state["actions"][0]["action"] == "free-disk-space"
    assert state["actions"][0]["status"] == "failed"
    assert isinstance(audit, list)
    assert audit[0]["event"] == "recovery-interrupted"

    target = state_reader.get_action_state("free-disk-space")
    assert target is not None
    assert target["status"] == "failed"

    assert state_path.is_relative_to(tmp_path)
    assert audit_path.is_relative_to(tmp_path)
