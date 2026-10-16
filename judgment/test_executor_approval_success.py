import os
import time
import unittest
from unittest.mock import Mock, patch

import redis

from backend.action_executor import (
    ActionExecutor,
    _PROCESS_TERMINATION_AUTHORITY,
)
from backend.core.auth.approval_service import (
    create_approval_request,
    decide_approval,
)


class RealApprovalExecutorIntegrationTests(unittest.TestCase):
    def test_valid_approval_reaches_dispatch_without_real_termination(self):
        client = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()

        try:
            for index, action in enumerate(
                ("kill_process", "kill_high_cpu_process")
            ):
                with self.subTest(action=action):
                    pid = 2147483000 + index
                    create_time = 1700000000.0 + index
                    name = f"approval-test-{index}-no-real-process.exe"

                    request = create_approval_request(
                        requested_by="integration-test-requester",
                        device_id="approval-test-device",
                        action=action,
                        pid=pid,
                        create_time=create_time,
                        name=name,
                        ttl_s=30,
                        client=client,
                    )

                    self.assertTrue(
                        decide_approval(
                            request["approval_id"],
                            approved=True,
                            decided_by="integration-test-reviewer",
                            client=client,
                        )
                    )

                    executor = ActionExecutor.__new__(ActionExecutor)
                    executor.agent = Mock()
                    executor.agent.encode_state.return_value = [0]
                    executor.simulator = Mock()
                    executor.simulator.apply_action.return_value = {}
                    executor.simulator.evaluate_state.return_value = 0

                    decision = {
                        "action": action,
                        "context": "general",
                        "target_name": name,
                        "target_pid": pid,
                        "target_create_time": create_time,
                        "baseline_cpu": 0,
                        "duration_seconds": 30,
                        "device_id": "approval-test-device",
                        "approval_id": request["approval_id"],
                    }

                    with patch.object(
                        executor, "get_metrics",
                        return_value={
                            "cpu": 100, "memory": 20, "disk": 20
                        }
                    ), patch(
                        "backend.action_executor.CausalEngine"
                    ) as causal, patch(
                        "backend.action_executor.is_action_allowed",
                        return_value=(True, "allowed")
                    ), patch(
                        "backend.action_executor.is_safe",
                        return_value=True
                    ), patch.object(
                        executor, "can_execute", return_value=True
                    ), patch(
                        "backend.action_executor.get_optimizer",
                        return_value={"reward_scale": 1.0}
                    ), patch.object(
                        executor, "_execute_action",
                        return_value={"status": "blocked"}
                    ) as dispatch, patch.object(
                        executor, "verify_outcome",
                        return_value={"verified": False}
                    ), patch(
                        "backend.core.auth.approval_service._redis_client",
                        return_value=client,
                    ), patch.object(
                        executor, "_compute_reward", return_value=0
                    ), patch(
                        "backend.action_executor.time.sleep"
                    ), patch(
                        "backend.action_executor.log_event"
                    ):
                        causal.return_value.detect.return_value = {
                            "primary_cause": {
                                "process": name,
                                "contributors": [],
                            }
                        }

                        result = executor.execute(decision, source="manual")

                    if result.get("status") == "blocked_approval":
                        record = client.hgetall(
                            "process:approval:" + request["approval_id"]
                        )
                        self.fail(
                            f"Approval denied: reason={result.get('reason')!r}; "
                            f"stored_status={record.get('status')!r}; "
                            f"stored_identity={{k: record.get(k) for k in "
                            f"('device_id', 'action', 'pid', 'create_time', 'name')}}; "
                            f"decision_identity={{k: decision.get(k) for k in "
                            f"('device_id', 'action', 'target_pid', "
                            f"'target_create_time', 'target_name')}}"
                        )
                    self.assertEqual(result["status"], "blocked")
                    dispatch.assert_called_once_with(
                        action,
                        name,
                        decision,
                        source="manual",
                        termination_authority=_PROCESS_TERMINATION_AUTHORITY,
                    )

                    # The approval has been consumed; replay must fail.
                    from backend.core.auth.approval_service import consume_approval

                    self.assertFalse(
                        consume_approval(
                            request["approval_id"],
                            device_id="approval-test-device",
                            action=action,
                            pid=pid,
                            create_time=create_time,
                            name=name,
                            client=client,
                        )
                    )

                    print(f"PASS: {action} accepted valid approval once")
                    print(f"PASS: {action} approval replay denied")
        finally:
            client.close()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        RealApprovalExecutorIntegrationTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)

