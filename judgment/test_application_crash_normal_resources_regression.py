from backend.intelligence_pipeline import run_intelligence_pipeline


def main():
    print("=== APPLICATION CRASH + NORMAL RESOURCES REGRESSION TEST ===")

    crashed_pid = 54321

    live_metrics = {
        "cpu": 25.0,
        "memory": 40.0,
        "disk": 35.0,
        "processes": [
            {
                "pid": crashed_pid,
                "name": "crashed_application.exe",
                "cpu": 20.0,
                "memory": 2.0,
                "status": "terminated",
                "exitcode": -1073741510,
                "crashed": True,
            }
        ],
    }

    result = run_intelligence_pipeline(
        allow_execution=False,
        live_metrics=live_metrics,
    )

    root = result.get("root_cause") or {}
    causal = result.get("causal") or {}
    processes = result.get("processes") or []
    decision = result.get("decision") or {}

    root_type = (
        root.get("causal_primary_type")
        or root.get("root_cause_type")
        or root.get("type")
    )

    primary = causal.get("primary_cause") or {}
    primary_type = (
        primary.get("causal_primary_type")
        or primary.get("root_cause_type")
        or primary.get("type")
    )

    print()
    print("ROOT CAUSE:")
    print(root)

    print()
    print("CAUSAL PRIMARY:")
    print(primary)

    print()
    print("PROCESS VIEW:")
    print(processes)

    print()
    print("DECISION:")
    print(decision)

    print()
    print("Extracted root_cause_type:", root_type)
    print("Extracted primary_cause_type:", primary_type)

    assert any(
        p.get("pid") == crashed_pid
        and p.get("name") == "crashed_application.exe"
        for p in processes
    ), "FAIL: crashed application was not preserved in process view"

    assert root_type not in (None, "background_load"), (
        "FAIL: application crash with normal resources was reduced to "
        f"{root_type!r}; causal layer needs an explicit crash/process-failure classification"
    )

    assert primary_type not in (None, "background_load"), (
        "FAIL: causal.primary_cause was reduced to "
        f"{primary_type!r}; crash evidence was not preserved"
    )

    print()
    print("PASS: application crash preserved as a causal condition.")


if __name__ == "__main__":
    main()
