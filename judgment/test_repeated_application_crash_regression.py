from backend.intelligence_pipeline import run_intelligence_pipeline


def make_process(pid, name="unstable_application.exe"):
    return {
        "pid": pid,
        "name": name,
        "cpu": 20.0,
        "memory": 2.0,
        "status": "terminated",
        "exitcode": 1,
        "crashed": True,
        "node": "local",
    }


def run_crash(label, pid):
    print()
    print(f"=== {label} ===")

    result = run_intelligence_pipeline(
        allow_execution=False,
        live_metrics={
            "cpu": 25.0,
            "memory": 40.0,
            "disk": 35.0,
            "processes": [make_process(pid)],
        },
    )

    root = result.get("root_cause") or {}
    causal = result.get("causal") or {}
    primary = causal.get("primary_cause") or {}
    decision = result.get("decision") or {}

    print("Root cause:", root.get("type"))
    print("Primary cause:", primary.get("type"))
    print("Confidence:", root.get("confidence"))
    print("Severity:", root.get("severity"))
    print("Risk:", root.get("propagated_risk"))
    print("Recommended action:", root.get("recommended_action"))
    print("Decision:", decision.get("action"))
    print("Auto execute:", decision.get("auto_execute"))
    print("Requires confirmation:", decision.get("requires_confirmation"))

    assert root.get("type") == "application_crash", (
        f"{label}: expected application_crash"
    )

    assert primary.get("type") == "application_crash", (
        f"{label}: expected primary application_crash"
    )

    assert decision.get("action") == "investigate", (
        f"{label}: expected investigate decision"
    )

    assert decision.get("auto_execute") is False, (
        f"{label}: automatic execution must remain disabled"
    )

    return result


def main():
    print("=== REPEATED APPLICATION CRASH REGRESSION ===")

    results = []

    results.append(run_crash("CRASH 1", 63001))
    results.append(run_crash("CRASH 2", 63002))
    results.append(run_crash("CRASH 3", 63003))

    print()
    print("==============================================")
    print("PASS: REPEATED APPLICATION CRASHES REMAIN SAFE")
    print("All crashes -> application_crash")
    print("All decisions -> investigate")
    print("Automatic remediation -> disabled")
    print("==============================================")


if __name__ == "__main__":
    main()
