import time
import psutil
from datetime import datetime, timezone

from backend.timeline_engine import log_event
from backend.experience_store import store_experience
from backend.safety_guard import is_safe
from backend.dqn_agent import ACTIONS as DQN_ACTIONS, DQNAgent
from backend.os_system.simulation_engine import SimulationEngine
from backend.core.causal_engine import CausalEngine
from backend.self_optimizer import update_optimizer, get_optimizer

from backend.action_history import record as record_action
from backend.os_system.action_feedback import penalize, is_blocked
from backend.policy_engine import is_action_allowed
from backend.core.actions.action_executor import ACTIONS, execute_action


COOLDOWN_SECONDS = 2
GLOBAL_COOLDOWN = 5

VERIFICATION_TARGETS = {
    "clear_temp": "disk",
    "clear_docker_cache": "disk",
    "clear_logs": "disk",
    "clear_pip_cache": "disk",
    "drop_caches": "memory",
}

# Actions that require an explicitly identified process target.
# Destructive process actions must continue through the existing
# PID + creation-time identity validation.
PROCESS_TARGET_ACTIONS = {
    "kill_process",
    "kill_high_cpu_process",
    "throttle_process",
}

# System-level actions operate on system resources rather than
# a specific process and therefore do not require target_name.
SYSTEM_ACTIONS = {
    "clear_temp",
    "clear_docker_cache",
    "clear_logs",
    "clear_pip_cache",
    "drop_caches",
}

SAFE_PROCESSES = [
    "system", "systemd", "init",
    "python", "bash", "services",
    "explorer.exe", "wininit"
]


class ActionExecutor:

    def __init__(self, agent=None):
        self.last_executed = {}
        self.last_global_action = 0

        self.agent = agent if agent is not None else DQNAgent()

        self.simulator = SimulationEngine({
            "cpu": {"memory": 0.3},
            "memory": {"cpu": 0.2},
            "disk": {"cpu": 0.25}
        })

    # ---------------------------------------------------------
    # 🔒 PROCESS SAFETY FILTER
    # ---------------------------------------------------------
    def is_killable(self, name):
        name = (name or "").lower()

        if not name:
            return False

        if any(x in name for x in ["idle", "system idle"]):
            return False

        if name in SAFE_PROCESSES:
            return False

        return True

    # ---------------------------------------------------------
    # COOLDOWN
    # ---------------------------------------------------------
    def can_execute(self, action, decision):

        if is_blocked(action):
            return False

        now = time.time()

        if now - self.last_global_action < GLOBAL_COOLDOWN:
            return False

        key = f"{action}_{decision.get('target_pid', 'global')}"
        last_time = self.last_executed.get(key, 0)

        if now - last_time > COOLDOWN_SECONDS:
            self.last_executed[key] = now
            self.last_global_action = now
            return True

        return False

    # ---------------------------------------------------------
    # METRICS
    # ---------------------------------------------------------
    def get_metrics(self):
        return {
            "cpu": psutil.cpu_percent(interval=0.5),
            "memory": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage('/').percent,
        }

    # ---------------------------------------------------------
    # VERIFY REAL-WORLD OUTCOME
    # ---------------------------------------------------------
    def verify_outcome(self, action, before, after, result):
        if result.get("status") != "executed":
            return {
                "status": "failed",
                "verified": False,
                "reason": "action_execution_failed",
            }

        metric = VERIFICATION_TARGETS.get(action)

        if not metric:
            return {
                "status": "unverified",
                "verified": False,
                "reason": "action_has_no_verified_metric",
            }

        delta = round(before[metric] - after[metric], 3)

        if delta > 0:
            outcome = "success"
        elif delta == 0:
            outcome = "partial"
        else:
            outcome = "failed"

        return {
            "status": outcome,
            "verified": outcome == "success",
            "metric": metric,
            "before": before[metric],
            "after": after[metric],
            "delta": delta,
            "expected_direction": "decrease",
        }

    # ---------------------------------------------------------
    # 🔥 MAIN EXECUTION
    # ---------------------------------------------------------
    def execute(self, decision):

        action = decision.get("action")
        context = decision.get("context", "general")
        baseline = decision.get("baseline_cpu", 50)
        duration = decision.get("duration_seconds", 0)

        if not action:
            return {"status": "no_action"}

        # ---------------- BEFORE ----------------
        before = self.get_metrics()

        # ---------------- CAUSAL ----------------
        causal = CausalEngine().detect(
            {
                "cpu_pct": before["cpu"],
                "mem_pct": before["memory"],
                "disk_pct": before["disk"]
            },
            {},
        )

        primary = causal.get("primary_cause", {})
        contributors = primary.get("contributors", [])

        target_name = primary.get("process") or decision.get("target_name")

        # Process actions require an explicitly identified target.
        # System-level actions do not.
        if action in PROCESS_TARGET_ACTIONS and not target_name:
            return {"status": "no_valid_target"}

        # ---------------- POLICY ----------------
        allowed, reason = is_action_allowed(
            action,
            context=context,
            target_name=target_name
        )

        if not allowed:
            return {"status": "blocked_policy", "reason": reason}

        # ---------------- SAFETY ----------------
        if not is_safe(action):
            return {"status": "blocked_by_safety"}

        if not self.can_execute(action, decision):
            return {"status": "cooldown_or_blocked"}

        # ---------------- CONTEXT ----------------
        if context == "gaming":
            return {"status": "ignored", "reason": "gaming session"}

        if context == "critical":
            return {"status": "blocked", "reason": "critical workload"}

        # ---------------- BASELINE ----------------
        # CPU baseline/duration gates apply to process/CPU remediation.
        # System-resource actions use their own policy and verification
        # instead of requiring a CPU spike.
        if action in PROCESS_TARGET_ACTIONS:
            if before["cpu"] < baseline + 20:
                return {"status": "ignored_normal_usage"}

            if duration < 10:
                return {"status": "ignored_short_spike"}

        # ---------------- STATE ----------------
        state = self.agent.encode_state(before)

        # ---------------- SIMULATION ----------------
        simulated = self.simulator.apply_action(before, action)
        sim_score = self.simulator.evaluate_state(simulated)

        opt = get_optimizer()
        reward_scale = opt.get("reward_scale", 1.0)

        if sim_score < -200 * reward_scale:
            return {
                "status": "blocked_simulation",
                "simulated": simulated
            }

        # ---------------- EXECUTION ----------------
        result = self._execute_action(action, target_name, decision)

        time.sleep(1)

        # ---------------- AFTER ----------------
        after = self.get_metrics()

        # ---------------- VERIFY ----------------
        verification = self.verify_outcome(
            action,
            before,
            after,
            result,
        )

        # ---------------- REWARD ----------------
        reward = self._compute_reward(before, after, result)

        next_state = self.agent.encode_state(after)

        if result.get("status") == "executed":
            # `action` is the canonical executor action. When a DQN action
            # was translated before execution, use the original DQN action
            # for replay so DQNAgent.remember() receives its own vocabulary.
            learning_action = decision.get("learning_action", action)

            self.agent.remember(
                state,
                learning_action,
                reward,
                next_state,
            )
            self.agent.train()

            store_experience(state.tolist(), action, reward, before, after, verification)
            update_optimizer("balanced", reward)
            record_action(action, reward)

            if reward < 0:
                penalize(action)

        # ---------------- EXPLANATION ----------------
        explanation = {
            "target": target_name,
            "cpu_before": before["cpu"],
            "cpu_after": after["cpu"],
            "improvement": round(before["cpu"] - after["cpu"], 2),
            "contributors": contributors[:3]
        }

        log_event({
            "time": datetime.now(timezone.utc).isoformat(),
            "event": f"Executed {action} on {target_name}",
            "reward": reward
        })

        result.update({
            "reward": reward,
            "before": before,
            "after": after,
            "verification": verification,
            "explanation": explanation
        })

        return result


    # ---------------------------------------------------------
    # SAFE SIMULATION LEARNING
    # ---------------------------------------------------------
    def simulate_learning_step(self, metrics, context=None):
        """Train the DQN from a simulated transition only."""
        if not isinstance(metrics, dict):
            return {"status": "invalid_metrics", "trained": False}

        state = self.agent.encode_state(metrics)
        action = self.agent.select_action(state)

        before_score = self.simulator.evaluate_state(
            metrics, context=context
        )

        # Evaluate all DQN actions once for comparison. These results
        # remain advisory and are NOT used as a hard teacher.
        candidate_actions = list(DQN_ACTIONS)
        candidates = []

        for candidate_action in candidate_actions:
            candidate_state = self.simulator.apply_action(
                metrics, candidate_action
            )
            candidate_safe, candidate_reason = (
                self.simulator.is_simulation_safe(
                    metrics, candidate_state
                )
            )
            candidate_score = self.simulator.evaluate_state(
                candidate_state, context=context
            )
            candidate_reward = round(
                candidate_score - before_score, 3
            )

            candidates.append({
                "action": candidate_action,
                "score": candidate_score,
                "reward": candidate_reward,
                "safe": candidate_safe,
                "reason": candidate_reason,
                "state": candidate_state,
            })

        safe_candidates = [
            item for item in candidates if item["safe"]
        ]

        best_candidate = (
            max(safe_candidates, key=lambda item: item["score"])
            if safe_candidates
            else None
        )

        # Train only on the action actually selected by the DQN.
        selected = next(
            item for item in candidates
            if item["action"] == action
        )

        simulated = selected["state"]
        safe = selected["safe"]
        safety_reason = selected["reason"]

        if not safe:
            return {
                "status": "blocked_simulation",
                "trained": False,
                "action": action,
                "reason": safety_reason,
                "simulated": simulated,
                "best_simulated_action": (
                    best_candidate["action"]
                    if best_candidate else None
                ),
            }

        reward = selected["reward"]
        after_score = selected["score"]
        next_state = self.agent.encode_state(simulated)

        self.agent.remember(
            state, action, reward, next_state
        )

        loss = self.agent.train()

        return {
            "status": "simulated",
            "trained": True,
            "action": action,
            "reward": reward,
            "before_score": before_score,
            "after_score": after_score,
            "simulated": simulated,
            "best_simulated_action": (
                best_candidate["action"]
                if best_candidate else None
            ),
            "best_simulated_reward": (
                best_candidate["reward"]
                if best_candidate else None
            ),
            "action_gap": (
                round(
                    best_candidate["reward"] - reward, 3
                )
                if best_candidate else None
            ),
            "candidates": candidates,
            "safety": {
                "safe": safe,
                "reason": safety_reason,
            },
            "loss": loss,
            "epsilon": self.agent.epsilon,
        }


    # ---------------------------------------------------------
    # ACTION HANDLER
    # ---------------------------------------------------------
    def _execute_action(self, action, target_name, decision):

        if action == "kill_process":
            # Destructive process termination MUST carry an exact identity.
            # PID alone is insufficient because operating systems reuse PIDs.
            expected_pid = decision.get("target_pid")
            expected_create_time = decision.get("target_create_time")

            if expected_pid is None or expected_create_time is None:
                return {
                    "status": "blocked",
                    "action": "kill_process",
                    "target": target_name,
                    "reason": "exact_process_identity_required",
                    "message": (
                        "Process termination requires PID and creation-time "
                        "identity. No process was terminated."
                    ),
                }

            return self.kill_process_by_name(
                target_name,
                expected_pid=expected_pid,
                expected_create_time=expected_create_time,
            )

        if action == "kill_high_cpu_process":
            # Destructive CPU remediation MUST use the exact process identity
            # selected by the decision engine. Never let a lower-level helper
            # independently choose "some" high-CPU process.
            expected_pid = decision.get("target_pid")
            expected_create_time = decision.get("target_create_time")

            if expected_pid is None or expected_create_time is None:
                return {
                    "status": "blocked",
                    "action": "kill_high_cpu_process",
                    "target": target_name,
                    "reason": "exact_process_identity_required",
                    "message": (
                        "High-CPU termination requires PID and creation-time "
                        "identity. No process was terminated."
                    ),
                }

            return self.kill_process_by_name(
                target_name,
                expected_pid=expected_pid,
                expected_create_time=expected_create_time,
            )

        if action == "throttle_process":
            return {"status": "executed", "action": "throttle"}

        canonical = execute_action(action, source="manual")

        return {
            "status": "executed" if canonical.get("success") else "failed",
            "action": action,
            "details": canonical,
        }

    # ---------------------------------------------------------
    # 🔥 SAFE PROCESS KILL
    # ---------------------------------------------------------
    def kill_process_by_name(self, target_name, expected_pid=None,
                             expected_create_time=None):
        """
        Terminate a process only after validating its identity.

        PID alone is not sufficient because operating systems can reuse PIDs.
        If expected_pid/create_time are supplied, both are validated before
        termination.  The process is terminated gracefully and its exit is
        verified.

        This method NEVER selects a process merely because its name matches.
        """

        if not target_name:
            return {
                "status": "blocked",
                "reason": "missing_target_name",
            }

        target_name = str(target_name)

        candidates = []

        for proc in psutil.process_iter(
            ["pid", "name", "create_time", "username", "cmdline"]
        ):
            try:
                info = proc.info
                name = info.get("name")

                if name != target_name:
                    continue

                candidates.append(proc)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception:
                continue

        if not candidates:
            return {
                "status": "not_found",
                "target": target_name,
                "reason": "no_matching_process",
            }

        # Never arbitrarily choose between multiple processes with the same
        # name. The caller must identify the exact process.
        if expected_pid is None and len(candidates) > 1:
            return {
                "status": "ambiguous_target",
                "target": target_name,
                "candidates": [
                    {
                        "pid": p.pid,
                        "name": p.info.get("name"),
                        "create_time": p.info.get("create_time"),
                    }
                    for p in candidates
                ],
                "reason": "multiple_processes_match_name",
            }

        proc = None

        if expected_pid is not None:
            try:
                expected_pid = int(expected_pid)
            except (TypeError, ValueError):
                return {
                    "status": "blocked",
                    "reason": "invalid_expected_pid",
                }

            for candidate in candidates:
                if candidate.pid == expected_pid:
                    proc = candidate
                    break

            if proc is None:
                return {
                    "status": "identity_mismatch",
                    "target": target_name,
                    "expected_pid": expected_pid,
                    "reason": "pid_does_not_match_target",
                }

        else:
            # Destructive execution must never infer a target from process name.
            # Even one matching process is insufficient because the identity
            # presented to the executor may be stale.
            return {
                "status": "blocked",
                "target": target_name,
                "reason": "exact_process_identity_required",
                "message": (
                    "PID and process creation time are required for "
                    "termination. No process was terminated."
                ),
            }

        try:
            # Re-read identity immediately before acting. This protects
            # against a PID being reused between discovery and execution.
            current = proc.as_dict(
                attrs=["pid", "name", "create_time", "username", "cmdline"]
            )

            if (current.get("name") or "").lower() != target_name.lower():
                return {
                    "status": "identity_mismatch",
                    "reason": "process_name_changed",
                }

            if expected_pid is not None and current.get("pid") != expected_pid:
                return {
                    "status": "identity_mismatch",
                    "reason": "pid_changed",
                }

            current_create_time = current.get("create_time")

            # Creation time is mandatory for destructive process identity.
            # Without it, a reused PID cannot be distinguished from the
            # original process.
            if current_create_time is None:
                return {
                    "status": "blocked",
                    "target": target_name,
                    "pid": proc.pid,
                    "reason": "process_create_time_unavailable",
                    "message": (
                        "The operating system did not provide process "
                        "creation time. Termination was refused."
                    ),
                }

            try:
                if abs(
                    float(current_create_time)
                    - float(expected_create_time)
                ) > 0.01:
                    return {
                        "status": "identity_mismatch",
                        "target": target_name,
                        "pid": proc.pid,
                        "expected_create_time": expected_create_time,
                        "actual_create_time": current_create_time,
                        "reason": "process_create_time_changed",
                        "message": (
                            "The PID now belongs to a different process "
                            "identity. Termination was refused."
                        ),
                    }
            except (TypeError, ValueError):
                return {
                    "status": "blocked",
                    "reason": "invalid_expected_create_time",
                }

            if not self.is_killable(current.get("name")):
                return {
                    "status": "blocked",
                    "reason": "protected_process",
                    "target": current.get("name"),
                    "pid": current.get("pid"),
                }

            # Never terminate PID 1 or the current Python backend process.
            if proc.pid in {1, psutil.Process().pid}:
                return {
                    "status": "blocked",
                    "reason": "critical_backend_process",
                    "pid": proc.pid,
                    "target": current.get("name"),
                }

            before = {
                "pid": current.get("pid"),
                "name": current.get("name"),
                "create_time": current.get("create_time"),
                "username": current.get("username"),
                "cmdline": current.get("cmdline"),
            }

            proc.terminate()

            try:
                proc.wait(timeout=5)
                exited = True
            except psutil.TimeoutExpired:
                exited = False

            if not exited:
                return {
                    "status": "terminate_timeout",
                    "action": "kill_process",
                    "target": current.get("name"),
                    "pid": current.get("pid"),
                    "create_time": current.get("create_time"),
                    "message": (
                        "Graceful termination timed out. "
                        "No force-kill was performed."
                    ),
                    "process": before,
                }

            return {
                "status": "executed",
                "action": "kill_process",
                "target": current.get("name"),
                "pid": current.get("pid"),
                "create_time": current.get("create_time"),
                "process": before,
                "termination": "graceful",
                "verified_exit": True,
            }

        except psutil.NoSuchProcess:
            return {
                "status": "already_exited",
                "target": target_name,
                "pid": expected_pid,
                "reason": "process_disappeared_before_termination",
            }

        except psutil.AccessDenied:
            return {
                "status": "access_denied",
                "target": target_name,
                "pid": expected_pid,
                "reason": "insufficient_process_permissions",
            }

        except Exception as exc:
            return {
                "status": "failed",
                "target": target_name,
                "pid": expected_pid,
                "reason": str(exc),
            }

    # ---------------------------------------------------------
    # REWARD
    # ---------------------------------------------------------
    def _compute_reward(self, before, after, result):

        if result.get("status") != "executed":
            return -0.5

        action = result.get("action")

        # Diagnostic actions observe the system but do not remediate it.
        if action == "kill_high_cpu":
            return 0.0

        cpu_gain = before["cpu"] - after["cpu"]
        mem_gain = before["memory"] - after["memory"]
        disk_gain = before["disk"] - after["disk"]

        # Reward the resource targeted by the action.
        if action in {
            "clear_temp",
            "clear_docker_cache",
            "clear_logs",
            "clear_pip_cache",
        }:
            reward = disk_gain

        elif action == "drop_caches":
            reward = mem_gain

        elif action in {
            "kill_process",
            "kill_high_cpu_process",
            "throttle_process",
        }:
            reward = cpu_gain * 1.5

        else:
            reward = cpu_gain * 1.5 + mem_gain

        if reward < 0:
            reward -= 1

        return round(reward, 3)
