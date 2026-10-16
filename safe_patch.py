from __future__ import annotations

import difflib
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time


def write_text_safely(path: Path, updated: str, *, apply: bool) -> bool:
    """Preview a text edit, or back it up and atomically replace the target."""
    path = path.resolve()
    original = path.read_text(encoding="utf-8")
    if original == updated:
        print(f"No changes needed: {path}")
        return False

    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=str(path),
        tofile=str(path),
    )
    print("".join(diff), end="")
    if not apply:
        print(f"Preview only; rerun with --apply to update {path}.")
        return False

    backup = path.with_name(f"{path.name}.bak-{time.time_ns()}")
    shutil.copy2(path, backup)

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, stat.S_IMODE(path.stat().st_mode))
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

    print(f"Updated {path}; original backed up to {backup}.")
    return True
