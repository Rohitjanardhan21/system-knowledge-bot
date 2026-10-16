import sys
import threading
from types import SimpleNamespace

from backend.core.demo import stress_engine
import stress_engine as root_stress_engine


def test_stress_scenarios_are_serialized(monkeypatch):
    def wait_for_stop(stop_event, _target_mb):
        stop_event.wait(timeout=2)

    monkeypatch.setattr(stress_engine, "_memory_stress_worker", wait_for_stop)

    started = stress_engine.start_scenario("memory_pressure")
    try:
        rejected = stress_engine.start_scenario("combined")

        assert started["success"] is True
        assert rejected["success"] is False
        assert "already running" in rejected["error"]
    finally:
        stress_engine.stop_all()


def test_cpu_stress_stops_at_the_configured_ceiling(monkeypatch):
    class FakeProcess:
        def start(self):
            return None

        def is_alive(self):
            return False

        def join(self, timeout=None):
            return None

    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(cpu_count=lambda logical=True: 1),
    )
    monkeypatch.setattr(
        stress_engine.multiprocessing,
        "Process",
        lambda **_kwargs: FakeProcess(),
    )
    monkeypatch.setattr(
        stress_engine,
        "_get_current_cpu_pct",
        lambda: stress_engine.CPU_CEILING,
    )
    stop_event = stress_engine.multiprocessing.Event()

    stress_engine._cpu_stress_worker(stop_event)

    assert stop_event.is_set()


def test_memory_stress_stops_at_the_configured_ceiling(monkeypatch):
    monkeypatch.setattr(
        stress_engine,
        "_get_current_memory_pct",
        lambda: stress_engine.MEMORY_CEILING,
    )
    stop_event = threading.Event()

    stress_engine._memory_stress_worker(stop_event, target_mb=20)

    assert stop_event.is_set()


def test_root_stress_engine_cleans_only_its_unique_temp_file(tmp_path, monkeypatch):
    owned_file = tmp_path / "cvis-stress-owned.tmp"
    unrelated_file = tmp_path / "unrelated.tmp"
    owned_file.write_text("owned", encoding="utf-8")
    unrelated_file.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        root_stress_engine,
        "create_temp_file",
        lambda prefix: str(owned_file),
    )
    stop_event = threading.Event()
    stop_event.set()

    root_stress_engine._disk_stress_worker(stop_event)

    assert not owned_file.exists()
    assert unrelated_file.read_text(encoding="utf-8") == "keep"
