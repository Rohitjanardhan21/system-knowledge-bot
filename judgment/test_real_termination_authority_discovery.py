import importlib
import inspect

def main():
    print("=== REAL TERMINATION AUTHORITY CALLABLE DISCOVERY ===")
    print("READ-ONLY.")
    print("NO PROCESS TERMINATION.")
    print("NO SYNTHETIC TELEMETRY.")
    print("NO FAILUREDNA.")
    print("NO DATABASE CHANGES.")

    agent = importlib.import_module("agent")

    print("\n1. AGENT MODULE")
    print("   module:", agent.__file__)

    candidates = []

    for name, obj in inspect.getmembers(agent, inspect.isfunction):
        try:
            sig = inspect.signature(obj)
        except (TypeError, ValueError):
            continue

        params = set(sig.parameters)

        if (
            "command_type" in params
            or "payload" in params
            or "command" in params
        ):
            candidates.append((name, str(sig)))

    print("\n2. CANDIDATE COMMAND/TERMINATION CALLABLES")

    if not candidates:
        print("   NONE FOUND")
    else:
        for name, sig in candidates:
            print(f"   {name}{sig}")

    print("\n3. EXPLICIT KILL HANDLER")
    kill_handler = getattr(agent, "action_kill_high_cpu", None)

    if kill_handler is None:
        print("   action_kill_high_cpu: NOT EXPORTED")
    else:
        print(
            "   action_kill_high_cpu:",
            inspect.signature(kill_handler),
        )
        print(
            "   NOTE: source contract says this function is "
            "diagnostic-only and does not terminate processes."
        )

    print("\n4. RESULT")

    if not candidates:
        print(
            "AUTHORITY CALLABLE NOT IDENTIFIED."
            " STOP BEFORE ANY DESTRUCTIVE TEST."
        )
        raise SystemExit(1)

    print(
        "AUTHORITY CALLABLE DISCOVERED."
        " NO DESTRUCTIVE ACTION WAS EXECUTED."
    )
    print("RESULT: PASS")

if __name__ == "__main__":
    main()
