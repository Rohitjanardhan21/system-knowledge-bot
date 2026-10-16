from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


AUDIT_PATH = Path("state/audit.json")
AUDIT_TEMP_PATH = AUDIT_PATH.with_suffix(".tmp")
AUDIT_LOCK_PATH = AUDIT_PATH.with_suffix(".lock")


@contextmanager
def _audit_lock():
    AUDIT_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    lock_file = AUDIT_LOCK_PATH.open("a+", encoding="utf-8")

    try:
        lock_file.seek(0)

        if os.name == "nt":
            try:
                msvcrt.locking(
                    lock_file.fileno(),
                    msvcrt.LK_LOCK,
                    1,
                )
            except OSError:
                lock_file.seek(0)
                msvcrt.locking(
                    lock_file.fileno(),
                    msvcrt.LK_LOCK,
                    1,
                )
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        yield

    finally:
        try:
            lock_file.seek(0)
            if os.name == "nt":
                msvcrt.locking(
                    lock_file.fileno(),
                    msvcrt.LK_UNLCK,
                    1,
                )
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass

        lock_file.close()


def _load_entries():
    if not AUDIT_PATH.exists():
        return []

    try:
        with AUDIT_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, list) else []

    except (json.JSONDecodeError, OSError):
        return []


def _cleanup_orphaned_temp():
    try:
        if AUDIT_TEMP_PATH.exists():
            AUDIT_TEMP_PATH.unlink()
    except OSError:
        pass


def _atomic_write_entries(entries):
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with AUDIT_TEMP_PATH.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())

    os.replace(AUDIT_TEMP_PATH, AUDIT_PATH)


def record_execution(results):
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(results, dict):
        results = [results]

    if not isinstance(results, list):
        raise TypeError(
            "Execution audit requires a dict or list of results."
        )

    with _audit_lock():
        _cleanup_orphaned_temp()

        entries = _load_entries()
        recorded = []

        for result in results:
            if not isinstance(result, dict):
                continue

            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "execution",
                **result,
            }

            entries.append(entry)
            recorded.append(entry)

        if recorded:
            _atomic_write_entries(entries)

        return recorded


def load_audit():
    return _load_entries()


def cleanup_audit_temp():
    with _audit_lock():
        _cleanup_orphaned_temp()


if __name__ == "__main__":
    cleanup_audit_temp()
    print("Audit temporary state cleaned.")
