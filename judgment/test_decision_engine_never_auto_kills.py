from pathlib import Path


def test_decision_engine_blocks_automatic_process_termination():
    source_path = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "decision_engine_v2.py"
    )
    source = source_path.read_text(encoding="utf-8")

    required_actions = {
        '"kill_process"',
        '"kill_high_cpu"',
        '"kill_high_cpu_process"',
    }

    guard_start = source.find(
        "# SAFETY: never auto-execute process termination."
    )
    assert guard_start >= 0, "Process-termination safety guard is missing"

    guard_end = source.find(
        "decision = self._build_decision(",
        guard_start,
    )
    assert guard_end >= 0, "Could not locate decision construction"

    guard = source[guard_start:guard_end]

    for action in required_actions:
        assert action in guard, f"Safety guard missing action: {action}"

    assert "auto_execute = False" in guard, (
        "Process-termination guard must disable automatic execution"
    )
