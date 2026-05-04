import os, time, threading, logging
from dataclasses import dataclass, asdict
from collections import deque

log = logging.getLogger("cvis.autoremediate")

def _get_mode():
    val = os.environ.get("AUTO_REMEDIATE", "false").lower().strip()
    if val in ("true","1","yes"): return "enabled"
    if val in ("dry_run","dryrun"): return "dry_run"
    return "disabled"

@dataclass
class RemediationEvent:
    event_id: str
    timestamp: float
    prediction_type: str
    action_id: str
    action_label: str
    mode: str
    result: dict
    notified: bool
    note: str = ""

class AutoRemediationEngine:
    MIN_CONFIDENCE = 85.0
    MIN_SEEN_COUNT = 15
    COOLDOWN_SECONDS = 1800
    MAX_ACTIONS_PER_HOUR = 3

    REMEDIATION_MAP = {
        "OOM":       [{"action_id":"drop_caches","label":"Drop Page Cache","min_confidence":85.0}],
        "DISK_FULL": [{"action_id":"clear_logs","label":"Rotate & Clear Logs","min_confidence":85.0},
                      {"action_id":"clear_temp","label":"Clear Temp Files","min_confidence":88.0}],
        "CPU_STRESS":[], "CRASH":[], "THERMAL":[],
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._audit_log = deque(maxlen=500)
        self._cooldowns = {}
        self._hourly_count = 0
        self._hour_start = time.time()
        self._notifier = None
        self._last_metrics = {}

    def set_notifier(self, notifier):
        self._notifier = notifier

    def update_metrics(self, metrics):
        self._last_metrics = metrics

    def evaluate(self, predictions, dna_summary):
        mode = _get_mode()
        now = time.time()
        if now - self._hour_start > 3600:
            self._hourly_count = 0
            self._hour_start = now
        if mode == "enabled" and self._hourly_count >= self.MAX_ACTIONS_PER_HOUR:
            return []

        pattern_map = {p["type"]:p for p in dna_summary.get("pattern_list",[])}
        events = []

        for pred in predictions:
            if pred.get("acknowledged") or pred.get("resolved"):
                continue
            pred_type = pred.get("type","")
            pred_conf = pred.get("confidence",0)
            severity  = pred.get("severity","LOW")

            if severity not in ("HIGH","CRITICAL"):
                continue
            if pred_conf < self.MIN_CONFIDENCE:
                continue

            pattern = pattern_map.get(pred_type,{})
            if pattern.get("seen",0) < self.MIN_SEEN_COUNT:
                self._notify(f"CVIS — {pred_type} Warning",
                    pred.get("message","") + " Manual action recommended.")
                continue

            actions = self.REMEDIATION_MAP.get(pred_type,[])
            if not actions:
                self._notify(f"CVIS — {pred_type} Predicted",
                    pred.get("message","") + " No automatic fix — check dashboard.")
                continue

            for ac in actions:
                action_id = ac["action_id"]
                if pred_conf < ac.get("min_confidence", self.MIN_CONFIDENCE):
                    continue
                last_run = self._cooldowns.get(action_id,0)
                if now - last_run < self.COOLDOWN_SECONDS:
                    continue

                event = self._act(pred, ac, mode)
                if event:
                    events.append(event)
                    if mode=="enabled" and event.result.get("success"):
                        self._cooldowns[action_id] = now
                        self._hourly_count += 1
        return events

    def _act(self, pred, ac, mode):
        action_id = ac["action_id"]
        label     = ac["label"]
        pred_type = pred.get("type","")
        pred_conf = pred.get("confidence",0)
        event_id  = f"ar_{action_id}_{int(time.time())}"

        if mode == "disabled":
            self._notify(f"CVIS — {pred_type} Predicted",
                f"{pred.get('message','')} Auto-fix disabled. Go to dashboard to act.")
            result = {"success":False,"skipped":True,"reason":"disabled"}
            note = "Notified user. No action taken."

        elif mode == "dry_run":
            self._notify(f"CVIS DRY RUN — {pred_type}",
                f"Would run: {label}. Set AUTO_REMEDIATE=true to enable.")
            result = {"success":False,"dry_run":True}
            note = f"DRY RUN: would have run {action_id}"

        else:
            self._notify(f"CVIS AUTO-FIX — {pred_type}",
                f"{pred_type} at {pred_conf:.0f}% confidence. Running: {label}.")
            try:
                from backend.core.actions.action_executor import execute_action
                result = execute_action(action_id)
            except Exception as e:
                result = {"success":False,"error":str(e)}
            if result.get("success"):
                self._notify(f"CVIS — {label} Complete","Auto-fix ran successfully.")
            else:
                self._notify(f"CVIS — Auto-fix Failed",
                    f"{label} failed. Manual action needed.")
            note = f"Executed. success={result.get('success')}"

        event = RemediationEvent(
            event_id=event_id, timestamp=time.time(),
            prediction_type=pred_type, action_id=action_id,
            action_label=label, mode=mode, result=result,
            notified=True, note=note,
        )
        with self._lock:
            self._audit_log.append(event)
        return event

    def _notify(self, title, message):
        try:
            if self._notifier:
                self._notifier.send(title=title, message=message)
            else:
                try:
                    from plyer import notification
                    notification.notify(title=title,message=message[:200],
                                        app_name="CVIS",timeout=10)
                except Exception:
                    pass
        except Exception:
            pass

    def get_audit_log(self, limit=50):
        with self._lock:
            return [asdict(e) for e in list(self._audit_log)[-limit:]]

    def get_status(self):
        mode = _get_mode()
        with self._lock:
            recent = [e for e in self._audit_log if time.time()-e.timestamp < 3600]
        return {
            "mode": mode,
            "enabled": mode=="enabled",
            "dry_run": mode=="dry_run",
            "actions_last_hour": len(recent),
            "actions_total": len(self._audit_log),
            "cooldowns": {k:round((self.COOLDOWN_SECONDS-(time.time()-v))/60)
                         for k,v in self._cooldowns.items()
                         if time.time()-v < self.COOLDOWN_SECONDS},
            "safe_actions": ["drop_caches","clear_logs","clear_temp"],
            "never_auto": ["kill_high_cpu","clear_docker_cache"],
        }

_ar_engine = None
_ar_lock = threading.Lock()

def get_ar_engine():
    global _ar_engine
    with _ar_lock:
        if _ar_engine is None:
            _ar_engine = AutoRemediationEngine()
    return _ar_engine
