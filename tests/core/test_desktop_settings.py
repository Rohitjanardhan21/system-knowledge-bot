import json

import pytest

from backend.desktop_settings import read_settings, write_settings


def test_missing_settings_default_to_on_demand(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "CVIS_DESKTOP_SETTINGS_PATH", str(tmp_path / "settings.json")
    )

    assert read_settings() == {
        "background_monitoring": False,
        "configured": False,
    }


@pytest.mark.parametrize("enabled", [True, False])
def test_settings_round_trip_atomically(monkeypatch, tmp_path, enabled):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("CVIS_DESKTOP_SETTINGS_PATH", str(path))

    result = write_settings(enabled)

    assert result == {
        "background_monitoring": enabled,
        "configured": True,
    }
    assert json.loads(path.read_text(encoding="utf-8")) == result
    assert read_settings() == result
    assert not list(tmp_path.glob("*.tmp"))


def test_write_requires_desktop_settings_path(monkeypatch):
    monkeypatch.delenv("CVIS_DESKTOP_SETTINGS_PATH", raising=False)

    with pytest.raises(RuntimeError, match="unavailable"):
        write_settings(True)
