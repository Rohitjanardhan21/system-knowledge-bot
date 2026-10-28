"""Persistent preferences for the locally packaged desktop application."""

import json
import os
import tempfile


def settings_path() -> str | None:
    return os.environ.get("CVIS_DESKTOP_SETTINGS_PATH")


def read_settings() -> dict:
    path = settings_path()
    if not path or not os.path.isfile(path):
        return {"background_monitoring": False, "configured": False}

    with open(path, encoding="utf-8") as settings_file:
        data = json.load(settings_file)

    return {
        "background_monitoring": bool(data.get("background_monitoring", False)),
        "configured": bool(data.get("configured", False)),
    }


def write_settings(background_monitoring: bool) -> dict:
    path = settings_path()
    if not path:
        raise RuntimeError("Desktop preferences are unavailable in this deployment")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "background_monitoring": background_monitoring,
        "configured": True,
    }
    fd, temporary_path = tempfile.mkstemp(
        prefix=".cvis-settings-", suffix=".tmp", dir=os.path.dirname(path)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as settings_file:
            json.dump(payload, settings_file)
            settings_file.flush()
            os.fsync(settings_file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise
    return payload
