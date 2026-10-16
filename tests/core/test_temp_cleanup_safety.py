import os
from pathlib import Path

from backend.core.actions import action_executor
from cvis_temp import cleanup_stale_temp_files


def test_cleanup_removes_only_stale_prefixed_files_in_managed_directory(tmp_path, monkeypatch):
    old_file = tmp_path / "cvis-old.tmp"
    recent_file = tmp_path / "cvis-recent.tmp"
    unrelated_file = tmp_path / "unrelated.tmp"
    nested_dir = tmp_path / "cvis-nested"

    old_file.write_text("old", encoding="utf-8")
    recent_file.write_text("recent", encoding="utf-8")
    unrelated_file.write_text("unrelated", encoding="utf-8")
    nested_dir.mkdir()
    (nested_dir / "keep.txt").write_text("keep", encoding="utf-8")

    old_timestamp = 1_000_000
    os.utime(old_file, (old_timestamp, old_timestamp))

    monkeypatch.setattr("cvis_temp.managed_temp_directory", lambda: tmp_path)

    removed, failed = cleanup_stale_temp_files(
        max_age_seconds=60,
    )

    assert (removed, failed) == (1, 0)
    assert not old_file.exists()
    assert recent_file.exists()
    assert unrelated_file.exists()
    assert (nested_dir / "keep.txt").exists()


def test_clear_temp_uses_managed_stale_file_cleanup(tmp_path, monkeypatch):
    stale_file = tmp_path / "cvis-cache.tmp"
    stale_file.write_text("cache", encoding="utf-8")
    old_timestamp = 1_000_000
    os.utime(stale_file, (old_timestamp, old_timestamp))

    monkeypatch.setattr("cvis_temp.managed_temp_directory", lambda: tmp_path)

    result = action_executor.action_clear_temp()

    assert result["success"] is True
    assert result["removed"] == 1
    assert not stale_file.exists()


def test_clear_logs_is_limited_to_regular_project_log_files(tmp_path, monkeypatch):
    log_file = tmp_path / "service.log"
    unrelated_file = tmp_path / "keep.txt"
    log_file.write_text("log contents", encoding="utf-8")
    unrelated_file.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(action_executor, "PROJECT_LOG_DIR", tmp_path)

    result = action_executor.action_clear_logs()

    assert result["success"] is True
    assert result["failed"] == 0
    assert log_file.read_text(encoding="utf-8") == ""
    assert unrelated_file.read_text(encoding="utf-8") == "keep"
