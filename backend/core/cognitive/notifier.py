"""
CVIS Notification Engine
========================
Sends OS-native notifications on Windows, macOS, and Linux.
Design principle: interrupt only when it matters.
One sentence. Two buttons. Disappears if ignored.
"""
import platform
import threading
import time
import logging
from dataclasses import dataclass
from typing import Optional, Callable

log = logging.getLogger("cvis.notifications")

OS = platform.system()

# ── Data structures ───────────────────────────────────────

@dataclass
class Notification:
    notif_id:    str
    title:       str
    message:     str
    severity:    str      # LOW / MEDIUM / HIGH / CRITICAL
    action_text: str      # button text
    sent_at:     float = 0.0
    dismissed:   bool = False


# ── Platform adapters ─────────────────────────────────────

class _WindowsNotifier:
    def __init__(self):
        self._available = False
        try:
            from plyer import notification as _n
            self._plyer = _n
            self._available = True
        except ImportError:
            try:
                import winrt.windows.ui.notifications as _wn
                self._available = True
                self._use_plyer = False
            except ImportError:
                pass

    def send(self, title: str, message: str, duration: int = 10) -> bool:
        if not self._available:
            return False
        try:
            self._plyer.notify(
                title=f"CVIS — {title}",
                message=message,
                app_name="CVIS AIOps",
                timeout=duration,
            )
            return True
        except Exception as e:
            log.debug(f"Windows notification failed: {e}")
            return False


class _MacNotifier:
    def __init__(self):
        self._available = False
        try:
            from plyer import notification as _n
            self._plyer = _n
            self._available = True
        except ImportError:
            import shutil
            self._available = bool(shutil.which("osascript"))

    def send(self, title: str, message: str, duration: int = 10) -> bool:
        try:
            if hasattr(self, '_plyer') and self._available:
                self._plyer.notify(
                    title=f"CVIS — {title}",
                    message=message,
                    app_name="CVIS AIOps",
                    timeout=duration,
                )
                return True
            # Fallback to osascript
            import subprocess
            script = f'display notification "{message}" with title "CVIS — {title}"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return True
        except Exception as e:
            log.debug(f"macOS notification failed: {e}")
            return False


class _LinuxNotifier:
    def __init__(self):
        import shutil
        self._notify_send = shutil.which("notify-send")
        self._available = bool(self._notify_send)
        if not self._available:
            try:
                from plyer import notification as _n
                self._plyer = _n
                self._available = True
            except ImportError:
                pass

    def send(self, title: str, message: str, duration: int = 10) -> bool:
        try:
            if self._notify_send:
                import subprocess
                subprocess.run([
                    self._notify_send,
                    f"CVIS — {title}",
                    message,
                    "--urgency=normal",
                    f"--expire-time={duration * 1000}",
                    "--icon=dialog-warning",
                ], capture_output=True, timeout=5)
                return True
            elif hasattr(self, '_plyer'):
                self._plyer.notify(
                    title=f"CVIS — {title}",
                    message=message,
                    timeout=duration,
                )
                return True
        except Exception as e:
            log.debug(f"Linux notification failed: {e}")
        return False


class _FallbackNotifier:
    """Prints to console when OS notifications unavailable."""
    def send(self, title: str, message: str, duration: int = 10) -> bool:
        border = "=" * 55
        print(f"\n{border}")
        print(f"  ⚠️  CVIS ALERT: {title}")
        print(f"  {message}")
        print(f"{border}\n")
        return True


# ── Notification Engine ───────────────────────────────────

class NotificationEngine:
    """
    Smart notification system.
    Decides when to interrupt the user and when to stay silent.
    """

    # Cooldown between notifications of the same type (seconds)
    COOLDOWN = {
        "LOW":      600,   # 10 minutes
        "MEDIUM":   300,   # 5 minutes
        "HIGH":     120,   # 2 minutes
        "CRITICAL": 60,    # 1 minute
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._last_sent: dict = {}      # severity → last sent time
        self._sent_types: dict = {}     # notification type → last sent time
        self._notifier = self._build_notifier()
        self._history: list = []
        self._enabled = True
        self._min_severity = "MEDIUM"   # only send MEDIUM and above by default

        log.info(f"Notification engine ready — OS: {OS}, backend: {type(self._notifier).__name__}")

    def _build_notifier(self):
        if OS == "Windows":
            n = _WindowsNotifier()
            if n._available:
                return n
        elif OS == "Darwin":
            n = _MacNotifier()
            if n._available:
                return n
        elif OS == "Linux":
            n = _LinuxNotifier()
            if n._available:
                return n
        return _FallbackNotifier()

    def should_notify(self, notif_type: str, severity: str) -> bool:
        """Decide if we should send a notification right now."""
        if not self._enabled:
            return False

        sev_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        if sev_order.get(severity, 0) < sev_order.get(self._min_severity, 1):
            return False

        now = time.time()
        with self._lock:
            # Check global cooldown for this severity
            last = self._last_sent.get(severity, 0)
            cooldown = self.COOLDOWN.get(severity, 300)
            if now - last < cooldown:
                return False

            # Check per-type cooldown
            type_last = self._sent_types.get(notif_type, 0)
            if now - type_last < cooldown * 2:
                return False

        return True

    def send(self, notif_type: str, title: str, message: str,
             severity: str = "MEDIUM", force: bool = False) -> bool:
        """Send a notification if cooldown allows."""
        if not force and not self.should_notify(notif_type, severity):
            return False

        now = time.time()
        duration = {"LOW": 6, "MEDIUM": 8, "HIGH": 12, "CRITICAL": 15}.get(severity, 8)

        sent = self._notifier.send(title, message, duration)

        if sent:
            with self._lock:
                self._last_sent[severity] = now
                self._sent_types[notif_type] = now
                self._history.append({
                    "type":     notif_type,
                    "title":    title,
                    "message":  message,
                    "severity": severity,
                    "sent_at":  now,
                })
                # Keep last 100 notifications
                if len(self._history) > 100:
                    self._history = self._history[-100:]

        return sent

    def send_prediction(self, prediction) -> bool:
        """Send a notification for a failure prediction."""
        severity = prediction.severity
        minutes  = int(prediction.minutes_remaining)
        title    = self._prediction_title(severity, minutes)
        message  = prediction.plain_message

        return self.send(
            notif_type=f"prediction_{prediction.failure_type}",
            title=title,
            message=message,
            severity=severity,
        )

    def send_health_alert(self, score: int, grade: str) -> bool:
        """Send notification when health score drops significantly."""
        if score > 600:
            return False

        severity = "CRITICAL" if score < 300 else "HIGH" if score < 450 else "MEDIUM"
        return self.send(
            notif_type="health_score",
            title=f"Health Score: {score} ({grade})",
            message=f"Your system health has dropped to {score}/1000. Check CVIS for details.",
            severity=severity,
        )

    def send_anomaly_alert(self, reason: str, severity: str) -> bool:
        """Send notification for anomaly detection."""
        if severity not in ("HIGH", "CRITICAL"):
            return False

        return self.send(
            notif_type="anomaly",
            title="System Anomaly Detected",
            message=reason,
            severity=severity,
        )

    def _prediction_title(self, severity: str, minutes: int) -> str:
        if severity == "CRITICAL":
            return f"⚠️ Critical — {minutes} min warning"
        elif severity == "HIGH":
            return f"High Risk — {minutes} min warning"
        else:
            return f"Heads up — {minutes} min warning"

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def set_min_severity(self, severity: str):
        """Set minimum severity level to trigger notifications."""
        if severity in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            self._min_severity = severity

    def get_history(self, limit: int = 20) -> list:
        with self._lock:
            return sorted(self._history, key=lambda x: x["sent_at"], reverse=True)[:limit]

    def get_status(self) -> dict:
        return {
            "enabled":       self._enabled,
            "min_severity":  self._min_severity,
            "backend":       type(self._notifier).__name__,
            "os":            OS,
            "sent_total":    len(self._history),
        }


# ── Singleton ─────────────────────────────────────────────
_notif_engine: Optional[NotificationEngine] = None
_notif_lock = threading.Lock()

def get_notifier() -> NotificationEngine:
    global _notif_engine
    with _notif_lock:
        if _notif_engine is None:
            _notif_engine = NotificationEngine()
    return _notif_engine
