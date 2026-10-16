from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from safe_patch import write_text_safely

TARGET = ROOT / "backend" / "action_executor.py"
APPLY = "--apply" in sys.argv

def patch_executor():
    source = TARGET.read_text(encoding="utf-8")

    import_line = "from backend.core.process_lifecycle import get_process_lifecycle_monitor"

    if import_line not in source:
        marker = "import psutil"
        if marker not in source:
            raise RuntimeError("Could not find psutil import anchor in backend/action_executor.py")
        source = source.replace(
            marker,
            marker + "\n" + import_line,
            1,
        )

    old = """            proc.terminate()

            try:
                proc.wait(timeout=5)
                exited = True
            except psutil.TimeoutExpired:
                exited = False
"""

    new = """            # Register the exact process identity as an expected termination
            # immediately before the destructive operation.  The lifecycle
            # monitor uses PID + creation time, so PID reuse cannot consume
            # this authorization.
            lifecycle_monitor = get_process_lifecycle_monitor()
            lifecycle_monitor.mark_expected_termination(
                int(current.get("pid")),
                float(current_create_time),
            )

            try:
                proc.terminate()
            except Exception:
                lifecycle_monitor.clear_expected_termination(
                    int(current.get("pid")),
                    float(current_create_time),
                )
                raise

            try:
                proc.wait(timeout=5)
                exited = True
            except psutil.TimeoutExpired:
                exited = False
"""

    if old not in source:
        if "lifecycle_monitor.mark_expected_termination(" in source:
            print("EXPECTED-TERMINATION BRIDGE ALREADY PRESENT.")
            return
        raise RuntimeError(
            "Could not find the exact proc.terminate() block. "
            "Refusing to patch an unknown location."
        )

    source = source.replace(old, new, 1)

    write_text_safely(TARGET, source, apply=APPLY)

def main():
    print("=== PREVIEW EXPECTED-TERMINATION AUTHORITY BRIDGE ===")
    print("TARGET:", TARGET)
    print("NO SYNTHETIC TELEMETRY.")
    print("NO MANUAL FAILUREDNA EVENT INJECTION.")
    print("PATCHING ONLY THE REAL DESTRUCTIVE TERMINATION PATH.")

    patch_executor()

    print(
        "\n=== PATCH PREVIEW COMPLETE ==="
        if not APPLY
        else "\n=== BRIDGE PATCH COMPLETE ==="
    )

if __name__ == "__main__":
    main()
