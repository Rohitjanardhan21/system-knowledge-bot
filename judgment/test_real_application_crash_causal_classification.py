import os
import signal
import subprocess
import sys
import time

from backend.intelligence_pipeline import run_intelligence_pipeline


def crash_target():
    time.sleep(60)


def main():
    print("=== REAL APPLICATION CRASH -> CAUSAL CLASSIFICATION TEST ===")

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
        ]
    )

    pid = process.pid

    print("Child PID:", pid)

    try:
        time.sleep(1)

        print("Child running:", process.poll() is None)

        # Terminate the real child process.
        process.terminate()
        exit_code = process.wait(timeout=10)

        print("Child exit code:", exit_code)

        assert exit_code is not None, "FAIL: child did not terminate"

        live_metrics = {
            "cpu": 25.0,
            "memory": 40.0,
            "disk": 35.0,
            "processes": [
                {
                    "pid": pid,
                    "name": "python.exe",
                    "cpu": 20.0,
                    "memory": 2.0,
                    "status": "terminated",
                    "exitcode": exit_code,
                    "crashed": True,
                    "node": "local",
                }
            ],
        }

        result = run_intelligence_pipeline(
            allow_execution=False,
            live_metrics=live_metrics,
        )

        root = result.get("root_cause") or {}
        causal = result.get("causal") or {}
        primary = causal.get("primary_cause") or {}
        decision = result.get("decision") or {}
        processes = result.get("processes") or []

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

        root_type = root.get("type")
        primary_type = primary.get("type")

        print()
        print("Root cause type:", root_type)
        print("Primary cause type:", primary_type)
        print("Recommended action:", root.get("recommended_action"))
        print("Decision action:", decision.get("action"))
        print("Auto execute:", decision.get("auto_execute"))
        print("Requires confirmation:", decision.get("requires_confirmation"))
        print("Executable:", decision.get("executable"))

        assert any(
            p.get("pid") == pid
            and p.get("crashed") is True
            for p in processes
        ), "FAIL: real crashed process was not preserved"

        assert root_type == "application_crash", (
            f"FAIL: expected application_crash, got {root_type!r}"
        )

        assert primary_type == "application_crash", (
            f"FAIL: expected primary application_crash, got {primary_type!r}"
        )

        assert root.get("recommended_action") == "investigate", (
            "FAIL: application crash should recommend investigation"
        )

        assert decision.get("action") == "investigate", (
            f"FAIL: expected investigate action, got {decision.get('action')!r}"
        )

        assert decision.get("auto_execute") is False, (
            "FAIL: real application crash must not auto-execute remediation"
        )

        assert decision.get("requires_confirmation") is True, (
            "FAIL: real application crash must require confirmation"
        )

        print()
        print("==============================================")
        print("PASS: REAL APPLICATION CRASH CAUSALLY CLASSIFIED")
        print("Real process -> crash -> attribution -> application_crash")
        print("Recommendation -> investigate")
        print("Automatic remediation -> disabled")
        print("==============================================")

    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
