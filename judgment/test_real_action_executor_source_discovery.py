import inspect
from backend.action_executor import ActionExecutor

def main():
    print("=== REAL ACTION EXECUTOR DESTRUCTIVE AUTHORITY DISCOVERY ===")
    print("READ-ONLY.")
    print("NO PROCESS TERMINATION.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO FAILUREDNA.")
    print("NO DATABASE CHANGES.")

    print("\nMODULE:")
    print(inspect.getfile(ActionExecutor))

    print("\nCLASS SIGNATURE:")
    try:
        print(inspect.signature(ActionExecutor))
    except Exception as exc:
        print("SIGNATURE ERROR:", repr(exc))

    print("\nTERMINATION-RELATED METHODS:")
    found = False

    for name, obj in inspect.getmembers(ActionExecutor):
        if not inspect.isfunction(obj):
            continue

        try:
            source = inspect.getsource(obj)
        except (OSError, TypeError):
            source = ""

        name_match = any(
            term in name.lower()
            for term in (
                "kill",
                "terminate",
                "process",
                "remediation",
                "execute",
            )
        )

        source_match = any(
            term in source.lower()
            for term in (
                "proc.terminate",
                ".terminate(",
                "process.terminate",
                "kill_high_cpu",
                "kill_process",
                "destructive process termination",
            )
        )

        if name_match or source_match:
            found = True
            try:
                sig = inspect.signature(obj)
            except (TypeError, ValueError):
                sig = "<signature unavailable>"

            print(f"\nMETHOD: {name}{sig}")
            print("SOURCE:")
            print(source)

    if not found:
        print("NO TERMINATION-RELATED METHODS FOUND.")

    print("\n=== RESULT ===")
    print("SOURCE DISCOVERY COMPLETE.")
    print("NO DESTRUCTIVE ACTION EXECUTED.")
    print("RESULT: PASS")

if __name__ == "__main__":
    main()
