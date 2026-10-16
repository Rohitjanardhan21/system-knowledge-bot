from pathlib import Path
import sys

from safe_patch import write_text_safely

ROOT = Path(__file__).resolve().parent
APPLY = "--apply" in sys.argv

path = ROOT / "judgment" / "lifecycle.py"
text = path.read_text(encoding="utf-8")

marker = "\ndef can_execute(action):\n"

new_function = r'''
def resolve_escalation(action):
    action = _resolve_action_record(action)

    with state_lock():
        retry_count = _get_retry_count(action)

        if not action.get("escalation_required"):
            return {
                "status": "blocked",
                "action": action.get("action"),
                "reason": "Action is not currently escalated.",
                "retry_count": retry_count,
                "escalation_required": False,
            }

        action["status"] = "approved"
        action["retry_count"] = 0
        action["max_retries"] = MAX_RETRIES
        action["escalation_required"] = False
        action["execution_mode"] = action.get(
            "execution_mode",
            "automatic",
        )

        action.pop("execution_started_at", None)
        action.pop("execution_completed_at", None)
        action.pop("execution_result", None)
        action.pop("recovery_reason", None)

        _persist_action(action)

        record_execution([{
            "event": "escalation-resolved",
            "action": action.get("action"),
            "status": "approved",
            "result": "escalation-resolved",
            "retry_count": 0,
            "max_retries": MAX_RETRIES,
            "escalation_required": False,
        }])

        return {
            "status": "approved",
            "action": action.get("action"),
            "reason": "Escalation explicitly resolved; execution re-authorized.",
            "retry_count": 0,
            "max_retries": MAX_RETRIES,
            "escalation_required": False,
        }

'''

if "def resolve_escalation(action):" not in text:
    if text.count(marker) != 1:
        raise SystemExit("Expected exactly one lifecycle insertion point.")
    text = text.replace(marker, new_function + marker)

write_text_safely(path, text, apply=APPLY)

path = ROOT / "judgment" / "retry.py"
text = path.read_text(encoding="utf-8")

if "    resolve_escalation,\n" not in text:
    if text.count("    retry_failed_action,\n") != 1:
        raise SystemExit("Expected exactly one retry import insertion point.")
    text = text.replace(
        "    retry_failed_action,\n",
        "    retry_failed_action,\n    resolve_escalation,\n",
        1,
    )

if '    "resolve_escalation",\n' not in text:
    if text.count('    "retry_failed_action",\n') != 1:
        raise SystemExit("Expected exactly one retry export insertion point.")
    text = text.replace(
        '    "retry_failed_action",\n',
        '    "retry_failed_action",\n    "resolve_escalation",\n',
        1,
    )

write_text_safely(path, text, apply=APPLY)
