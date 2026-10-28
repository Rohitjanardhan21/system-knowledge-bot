import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from judgment import lifecycle, state_lock


@pytest.mark.skipif(os.name != "nt", reason="Windows replace locks are transient")
def test_persist_action_retries_transient_windows_replace_denial(
    tmp_path: Path,
    monkeypatch,
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "latest.json"
    state_path.write_text(
        json.dumps({"actions": [{"action": "free-disk-space"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(lifecycle, "STATE_PATH", state_path)
    monkeypatch.setattr(
        lifecycle,
        "state_lock",
        lambda: state_lock.state_lock(state_dir / "state.lock"),
    )

    action = {
        "action": "free-disk-space",
        "status": "executed",
        "execution_result": "success",
    }
    replace = os.replace
    attempts = 0

    def transiently_denied(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("temporary file-sharing denial")
        replace(source, destination)

    with patch("judgment.lifecycle.os.replace", side_effect=transiently_denied):
        lifecycle._persist_action(action)

    assert attempts == 2
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["actions"][0]["status"] == "executed"
