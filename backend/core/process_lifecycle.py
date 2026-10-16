
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import psutil

EXPECTED_TERMINATION_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float
    name: str
    exe: str
    ppid: int


@dataclass
class TrackedProcess:
    identity: ProcessIdentity
    process: psutil.Process
    first_seen: float
    last_seen: float


class ProcessLifecycleMonitor:
    """
    Real process lifecycle tracker.

    Identity is PID + creation time. PID alone is never sufficient because
    operating systems can reuse PIDs.

    The monitor enumerates the complete process table instead of relying on
    the production /os/processes top-10 snapshot. This prevents ranking
    changes from looking like process termination.

    A process is only eligible for termination classification after it has
    actually been observed by this monitor.

    Normal exit code 0 is ignored.
    Non-zero exit codes are reported as unexpected termination unless the
    process identity was explicitly marked as expected to terminate.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._tracked: dict[tuple[int, float], TrackedProcess] = {}
        self._reported: set[tuple[int, float]] = set()
        self._expected: dict[tuple[int, float], float] = {}

    @staticmethod
    def _identity(proc: psutil.Process) -> Optional[ProcessIdentity]:
        try:
            with proc.oneshot():
                return ProcessIdentity(
                    pid=int(proc.pid),
                    create_time=float(proc.create_time()),
                    name=str(proc.name() or "unknown"),
                    exe=str(proc.exe() or ""),
                    ppid=int(proc.ppid()),
                )
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
            OSError,
            ValueError,
        ):
            return None

    def mark_expected_termination(
        self,
        pid: int,
        create_time: float,
    ) -> bool:
        """Register one exact process identity with bounded expiry."""
        key = (int(pid), float(create_time))
        expires_at = time.monotonic() + EXPECTED_TERMINATION_TTL_SECONDS
        with self._lock:
            self._expected[key] = expires_at
            return True

    def clear_expected_termination(
        self,
        pid: int,
        create_time: float,
    ) -> None:
        with self._lock:
            self._expected.pop((int(pid), float(create_time)), None)

    def tracked_identities(self) -> list[ProcessIdentity]:
        with self._lock:
            return [
                tracked.identity
                for tracked in self._tracked.values()
            ]

    def observe_and_detect(
        self,
        on_unexpected_termination: Optional[
            Callable[[dict], None]
        ] = None,
    ) -> list[dict]:
        """
        Take one complete real process-table observation and detect
        processes that terminated since the previous observation.
        """

        now = time.time()
        monotonic_now = time.monotonic()
        with self._lock:
            expired = [
                key for key, expires_at in self._expected.items()
                if expires_at <= monotonic_now
            ]
            for key in expired:
                self._expected.pop(key, None)

        current: dict[tuple[int, float], TrackedProcess] = {}

        try:
            processes = list(
                psutil.process_iter(
                    ["pid", "name", "exe", "ppid", "create_time", "status"]
                )
            )
        except Exception:
            return []

        for proc in processes:
            try:
                if proc.info.get("status") == psutil.STATUS_ZOMBIE:
                    continue
            except Exception:
                pass

            identity = self._identity(proc)

            if identity is None:
                continue

            key = (identity.pid, identity.create_time)

            with self._lock:
                previous = self._tracked.get(key)

            current[key] = TrackedProcess(
                identity=identity,
                process=proc,
                first_seen=(
                    previous.first_seen
                    if previous is not None
                    else now
                ),
                last_seen=now,
            )

        terminated: list[dict] = []

        with self._lock:
            previous_items = list(self._tracked.items())

            self._tracked = current

            for key, tracked in previous_items:
                if key in current:
                    continue

                if key in self._reported:
                    continue

                # The PID may have been reused. A different create_time
                # produces a different identity and therefore cannot match.
                proc = tracked.process

                try:
                    exit_code = proc.wait(timeout=0)
                except psutil.TimeoutExpired:
                    # The process is still alive but temporarily absent from
                    # enumeration. Do not classify it as terminated yet.
                    self._tracked[key] = tracked
                    continue
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    OSError,
                ):
                    # The process handle disappeared, but we cannot prove
                    # the termination result. Do not classify disappearance
                    # alone as a crash.
                    continue

                # A missing exit code is insufficient evidence of abnormal
                # termination. This is especially important on Windows,
                # where a process can disappear from enumeration before a
                # usable exit code is available.
                if exit_code is None:
                    self._tracked[key] = tracked
                    continue

                expected_until = self._expected.get(key)
                expected = (
                    expected_until is not None
                    and expected_until > time.monotonic()
                )
                self._expected.pop(key, None)

                event = {
                    "event_type": "PROCESS_TERMINATION",
                    "pid": tracked.identity.pid,
                    "create_time": tracked.identity.create_time,
                    "name": tracked.identity.name,
                    "exe": tracked.identity.exe,
                    "ppid": tracked.identity.ppid,
                    "exit_code": exit_code,
                    "expected": expected,
                    "first_seen": tracked.first_seen,
                    "last_seen": tracked.last_seen,
                    "observed_at": now,
                }

                self._reported.add(key)
                self._expected.pop(key, None)

                # Exit code 0 is a normal process completion.
                # Expected termination is also not a crash.
                if exit_code == 0 or expected:
                    continue

                event["event_type"] = "PROCESS_CRASH"
                terminated.append(event)

        if on_unexpected_termination is not None:
            for event in terminated:
                on_unexpected_termination(dict(event))

        return terminated


_process_lifecycle_monitor = ProcessLifecycleMonitor()


def get_process_lifecycle_monitor() -> ProcessLifecycleMonitor:
    return _process_lifecycle_monitor
