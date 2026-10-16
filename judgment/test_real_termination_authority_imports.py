import importlib
import inspect

def inspect_module(module_name):
    print(f"\n--- {module_name} ---")

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        print("IMPORT FAILED:", type(exc).__name__, str(exc))
        return False

    print("module:", getattr(module, "__file__", None))

    found = False

    for name, obj in inspect.getmembers(module):
        if inspect.isfunction(obj) or inspect.isclass(obj):
            try:
                source = inspect.getsource(obj)
            except (OSError, TypeError):
                source = ""

            if (
                "kill_high_cpu" in name.lower()
                or "proc.terminate" in source
                or "process termination" in source.lower()
                or "process remediation" in source.lower()
            ):
                try:
                    signature = inspect.signature(obj)
                except (TypeError, ValueError):
                    signature = "<signature unavailable>"

                print(f"{name}{signature}")
                print("  type:", type(obj).__name__)
                found = True

    if not found:
        print("No termination-related exported callable found.")

    return True


def main():
    print("=== REAL TERMINATION AUTHORITY IMPORT DISCOVERY ===")
    print("READ-ONLY.")
    print("NO PROCESS TERMINATION.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO FAILUREDNA.")
    print("NO DATABASE CHANGES.")

    ok1 = inspect_module("backend.action_executor")
    ok2 = inspect_module("backend.core.actions.action_executor")

    print("\n=== RESULT ===")

    if not (ok1 or ok2):
        raise SystemExit(1)

    print("REAL TERMINATION MODULE(S) IMPORTED.")
    print("NO DESTRUCTIVE ACTION EXECUTED.")
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
