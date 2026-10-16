from backend.core.process_lifecycle import (
    ProcessLifecycleMonitor,
    get_process_lifecycle_monitor,
)


def test_process_lifecycle_monitor_can_be_created_and_queried():
    monitor = ProcessLifecycleMonitor()

    assert isinstance(get_process_lifecycle_monitor(), ProcessLifecycleMonitor)
    assert isinstance(monitor.tracked_identities(), list)
