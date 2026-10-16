from backend.intelligence_pipeline import run_intelligence_pipeline


def run_case(name, metrics, expected):
    print()
    print(f"=== {name} ===")

    result = run_intelligence_pipeline(
        allow_execution=False,
        live_metrics=metrics,
    )

    root = result.get("root_cause") or {}
    causal = result.get("causal") or {}
    primary = causal.get("primary_cause") or {}

    root_type = root.get("type")
    primary_type = primary.get("type")

    decision = result.get("decision") or {}

    print("Root cause type:", root_type)
    print("Primary cause type:", primary_type)
    print("Recommended action:", root.get("recommended_action"))
    print("Decision action:", decision.get("action"))
    print("Auto execute:", decision.get("auto_execute"))
    print("Requires confirmation:", decision.get("requires_confirmation"))

    assert root_type == expected, (
        f"{name}: expected root cause {expected!r}, got {root_type!r}"
    )

    assert primary_type == expected, (
        f"{name}: expected primary cause {expected!r}, got {primary_type!r}"
    )

    assert decision.get("auto_execute") is False, (
        f"{name}: remediation must not auto-execute"
    )

    return result


def main():
    print("=== POST-FIX THREE-WAY CAUSAL REGRESSION ===")

    # ---------------------------------------------------------
    # CASE A: CPU overload
    # ---------------------------------------------------------
    run_case(
        "CASE A — CPU OVERLOAD",
        {
            "cpu": 99.0,
            "memory": 40.0,
            "disk": 35.0,
            "processes": [
                {
                    "pid": 61001,
                    "name": "cpu_worker.exe",
                    "cpu": 100.0,
                    "memory": 2.0,
                    "status": "running",
                }
            ],
        },
        "cpu_overload",
    )

    # ---------------------------------------------------------
    # CASE B: Memory pressure
    # ---------------------------------------------------------
    run_case(
        "CASE B — MEMORY PRESSURE",
        {
            "cpu": 20.0,
            "memory": 95.0,
            "disk": 35.0,
            "processes": [
                {
                    "pid": 61002,
                    "name": "memory_worker.exe",
                    "cpu": 5.0,
                    "memory": 80.0,
                    "status": "running",
                }
            ],
        },
        "memory_pressure",
    )

    # ---------------------------------------------------------
    # CASE C: Normal resources + crashed process
    # ---------------------------------------------------------
    run_case(
        "CASE C — APPLICATION CRASH",
        {
            "cpu": 25.0,
            "memory": 40.0,
            "disk": 35.0,
            "processes": [
                {
                    "pid": 61003,
                    "name": "crashed_application.exe",
                    "cpu": 20.0,
                    "memory": 2.0,
                    "status": "terminated",
                    "exitcode": -1073741510,
                    "crashed": True,
                }
            ],
        },
        "application_crash",
    )

    print()
    print("==============================================")
    print("PASS: ALL THREE CAUSAL CLASSIFICATIONS HOLD")
    print("CPU overload      -> cpu_overload")
    print("Memory pressure   -> memory_pressure")
    print("Application crash -> application_crash")
    print("Execution         -> disabled in every case")
    print("==============================================")


if __name__ == "__main__":
    main()
