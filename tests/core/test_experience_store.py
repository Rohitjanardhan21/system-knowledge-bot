import json

import pytest

from backend import experience_store as store


def record(action="test"):
    return {
        "state": [1, 2],
        "action": action,
        "reward": 0.5,
        "before": {"cpu": 80},
        "after": {"cpu": 60},
        "verification": {"verified": True},
    }


def test_missing_file_creates_new_history(tmp_path, monkeypatch):
    path = tmp_path / "experiences.json"
    monkeypatch.setattr(store, "PATH", str(path))

    experience_id = store.store_experience(**record())

    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["action"] == "test"
    assert "time" in data[0]
    assert data[0]["experience_id"] == experience_id


def test_verified_experience_can_be_consumed_for_feedback_once(
    tmp_path, monkeypatch
):
    path = tmp_path / "experiences.json"
    monkeypatch.setattr(store, "PATH", str(path))

    experience_id = store.store_experience(
        **{
            **record("monitor"),
            "verification": {"status": "success", "verified": True},
        }
    )

    assert store.consume_verified_experience(
        experience_id, "monitor"
    ) == {"status": "success", "verified": True}
    assert store.consume_verified_experience(experience_id, "monitor") is None


@pytest.mark.parametrize(
    "verification",
    [
        None,
        {"status": "unverified", "verified": False},
        {"status": "success", "verified": False},
        {"status": "failed", "verified": True},
    ],
)
def test_unverified_experience_cannot_be_consumed_for_feedback(
    tmp_path, monkeypatch, verification
):
    path = tmp_path / "experiences.json"
    monkeypatch.setattr(store, "PATH", str(path))

    experience_id = store.store_experience(
        **{**record("monitor"), "verification": verification}
    )

    assert store.consume_verified_experience(
        experience_id, "monitor"
    ) is None


def test_existing_history_is_preserved(tmp_path, monkeypatch):
    path = tmp_path / "experiences.json"
    path.write_text(json.dumps([{"action": "existing"}]), encoding="utf-8")
    monkeypatch.setattr(store, "PATH", str(path))

    store.store_experience(**record("new"))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert [item["action"] for item in data] == ["existing", "new"]


def test_malformed_json_is_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "experiences.json"
    original = '{"existing": '
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(store, "PATH", str(path))

    with pytest.raises(json.JSONDecodeError):
        store.store_experience(**record())

    assert path.read_text(encoding="utf-8") == original


def test_non_list_json_is_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "experiences.json"
    original = '{"action": "existing"}'
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(store, "PATH", str(path))

    with pytest.raises(ValueError, match="JSON list"):
        store.store_experience(**record())

    assert path.read_text(encoding="utf-8") == original


def test_only_newest_500_records_are_retained(tmp_path, monkeypatch):
    path = tmp_path / "experiences.json"
    original = [{"action": f"old-{i}"} for i in range(500)]
    path.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(store, "PATH", str(path))

    store.store_experience(**record("newest"))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 500
    assert data[0]["action"] == "old-1"
    assert data[-1]["action"] == "newest"


def test_replace_failure_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "experiences.json"
    original = json.dumps([{"action": "existing"}])
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(store, "PATH", str(path))

    def fail_replace(source, destination):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(store.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replacement failure"):
        store.store_experience(**record("new"))

    assert path.read_text(encoding="utf-8") == original
