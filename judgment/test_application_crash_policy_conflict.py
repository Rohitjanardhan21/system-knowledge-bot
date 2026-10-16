from backend.intelligence_pipeline import run_intelligence_pipeline


def main():
    print("=== APPLICATION CRASH vs POLICY CONFLICT TEST ===")

    crashed_pid = 62001

    result = run_intelligence_pipeline(
        allow_execution=False,
        live_metrics={
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
                    "exitcode": 1,
                    "crashed": True,
                    "node": "local",
                }
            ],
        },
    )

    root = result.get("root_cause") or {}
    causal = result.get("causal") or {}
    primary = causal.get("primary_cause") or {}
    decision = result.get("decision") or {}

    causal_type = root.get("type")
    primary_type = primary.get("type")

    decision_action = decision.get("action")
    policy_action = decision.get("policy_action")
    dqn_action = decision.get("dqn_action")
    causal_action = decision.get("causal_action")

    print()
    print("Causal type:", causal_type)
    print("Primary type:", primary_type)
    print("Causal recommendation:", root.get("recommended_action"))
    print("Final decision:", decision_action)
    print("Policy action:", policy_action)
    print("DQN action:", dqn_action)
    print("Causal action:", causal_action)
    print("Auto execute:", decision.get("auto_execute"))
    print("Requires confirmation:", decision.get("requires_confirmation"))
    print("Executable:", decision.get("executable"))

    assert causal_type == "application_crash", (
        f"FAIL: expected application_crash, got {causal_type!r}"
    )

    assert primary_type == "application_crash", (
        f"FAIL: expected primary application_crash, got {primary_type!r}"
    )

    assert root.get("recommended_action") == "investigate", (
        "FAIL: causal layer did not recommend investigation"
    )

    # The critical safety invariant:
    # resource-oriented policy/DQN suggestions must not override
    # the causal application-crash decision.
    assert decision_action == "investigate", (
        f"FAIL: policy overrode application-crash decision with "
        f"{decision_action!r}"
    )

    assert decision.get("auto_execute") is False, (
        "FAIL: application-crash conflict must never auto-execute"
    )

    assert decision.get("requires_confirmation") is True, (
        "FAIL: application-crash decision must require confirmation"
    )

    assert decision.get("executable") is False, (
        "FAIL: application-crash investigation must not be treated "
        "as directly executable remediation"
    )

    print()
    print("==============================================")
    print("PASS: APPLICATION-CRASH CAUSAL AUTHORITY HOLDS")
    print("Causal diagnosis  -> application_crash")
    print("Causal action     -> investigate")
    print("Final decision    -> investigate")
    print("Policy/DQN cannot override causal diagnosis")
    print("Automatic action  -> disabled")
    print("==============================================")


if __name__ == "__main__":
    main()
