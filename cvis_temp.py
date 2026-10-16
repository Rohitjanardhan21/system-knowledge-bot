from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import time


STALE_TEMP_AGE_SECONDS = 24 * 60 * 60


def managed_temp_directory() -> Path:
    """Return a private, per-user directory for CVIS temporary files."""
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        directory = root / "CVIS" / "Temp"
    else:
        directory = Path.home() / ".cache" / "cvis" / "temp"

    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = directory.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise OSError(f"CVIS temp path is not a real directory: {directory}")

    if os.name != "nt":
        if metadata.st_uid != os.getuid():
            raise OSError(f"CVIS temp directory is not owned by this user: {directory}")
        directory.chmod(0o700)

    return directory


def cleanup_stale_temp_files(
    prefix: str = "cvis-",
    max_age_seconds: float = STALE_TEMP_AGE_SECONDS,
) -> tuple[int, int]:
    """Remove only old, regular files with the CVIS prefix in its private temp dir."""
    directory = managed_temp_directory()
    cutoff = time.time() - max_age_seconds
    removed = 0
    failed = 0

    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.name.startswith(prefix) or entry.is_symlink():
                continue

            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                metadata = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_mtime > cutoff:
                    continue
                os.unlink(entry.path)
                removed += 1
            except OSError:
                failed += 1

    return removed, failed


def create_temp_file(prefix: str = "cvis-") -> Path:
    """Create an exclusively named CVIS temp file and return its path."""
    fd, path = tempfile.mkstemp(prefix=prefix, dir=managed_temp_directory())
    os.close(fd)
    return Path(path)
