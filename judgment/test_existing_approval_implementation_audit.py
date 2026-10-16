from pathlib import Path


def test_approval_implementation_sources_are_available():
    repository_root = Path(__file__).resolve().parents[1]
    targets = (
        "backend/core/auth/auth.py",
        "backend/action_executor.py",
        "backend/core/actions/action_executor.py",
        "agent.py",
    )

    for relative_path in targets:
        source_path = repository_root / relative_path
        assert source_path.is_file(), f"Missing approval source: {relative_path}"
        assert source_path.stat().st_size > 0, (
            f"Empty approval source: {relative_path}"
        )
