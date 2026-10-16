from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import threading

if os.name == "nt":
    import msvcrt
else:
    import fcntl


STATE_LOCK_PATH = Path("state") / "state.lock"
_THREAD_LOCK = threading.RLock()


@contextmanager
def state_lock(lock_path=STATE_LOCK_PATH):
    with _THREAD_LOCK:
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        lock_file = lock_path.open("a+")

        try:
            lock_file.seek(0)

            if os.name == "nt":
                while True:
                    try:
                        msvcrt.locking(
                            lock_file.fileno(),
                            msvcrt.LK_NBLCK,
                            1,
                        )
                        break
                    except OSError:
                        import time
                        time.sleep(0.01)
                        lock_file.seek(0)
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
