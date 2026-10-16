from backend.core.process_lifecycle import (
    ProcessIdentity,
    ProcessLifecycleMonitor,
    TrackedProcess,
)


class FakeProcess:
    def __init__(self, exit_code):
        self.exit_code = exit_code

    def wait(self, timeout=0):
        return self.exit_code


def make_tracked_monitor(monkeypatch, expiry):
    monitor = ProcessLifecycleMonitor()
    key = (1234, 10.0)
    identity = ProcessIdentity(
        pid=1234,
        create_time=10.0,
        name="worker",
        exe="",
        ppid=1,
    )
    monitor._tracked[key] = TrackedProcess(
        identity=identity,
        process=FakeProcess(1),
        first_seen=1.0,
        last_seen=2.0,
    )
    monkeypatch.setattr(
        "backend.core.process_lifecycle.psutil.process_iter",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "backend.core.process_lifecycle.time.monotonic",
        lambda: 100.0,
    )
    monitor._expected[key] = expiry
    return monitor, key


def test_unexpired_expected_termination_does_not_report_crash(monkeypatch):
    monitor, key = make_tracked_monitor(monkeypatch, expiry=110.0)

    events = monitor.observe_and_detect()

    assert events == []
    assert key not in monitor._expected


def test_expired_expected_marker_does_not_suppress_crash(monkeypatch):
    monitor, key = make_tracked_monitor(monkeypatch, expiry=99.0)

    events = monitor.observe_and_detect()

    assert len(events) == 1
    assert events[0]["event_type"] == "PROCESS_CRASH"
    assert events[0]["pid"] == key[0]
    assert events[0]["expected"] is False
    assert key not in monitor._expected
