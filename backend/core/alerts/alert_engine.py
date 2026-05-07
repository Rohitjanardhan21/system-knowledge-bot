"""
CVIS v9 — Alert Engine
Supports: webhooks (async HTTP POST), email (SMTP/TLS), Slack-compatible payloads.
Features: per-rule cooldowns, severity levels, alert history, rule management.

Email alerts now use the weekly_report.py send_alert_email() function
which sends a beautiful HTML email with metric cards and action items.
"""
import asyncio, time, uuid, json, logging, os
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx

log = logging.getLogger("cvis.alerts")


# ─────────────────────────────────────────────────────────
#  Data models
# ─────────────────────────────────────────────────────────

@dataclass
class AlertRule:
    rule_id:     str
    name:        str
    metric:      str    # "cpu" | "mem" | "disk" | "ensemble" | "health"
    operator:    str    # "gt" | "lt" | "gte" | "lte"
    threshold:   float
    severity:    str    # "INFO" | "WARNING" | "HIGH" | "CRITICAL"
    cooldown_s:  int   = 60
    enabled:     bool  = True
    message_tpl: str   = "{metric} is {value:.2f} (threshold: {threshold})"


@dataclass
class FiredAlert:
    alert_id:    str
    rule_id:     str
    severity:    str
    message:     str
    metrics:     dict
    fired_at:    float
    resolved_at: Optional[float] = None
    sent_to:     list = field(default_factory=list)


@dataclass
class WebhookTarget:
    id:      str
    url:     str
    name:    str
    secret:  str  = ""
    enabled: bool = True
    retries: int  = 3
    sent:    int  = 0
    failed:  int  = 0


@dataclass
class EmailConfig:
    host:      str
    port:      int  = 587
    username:  str  = ""
    password:  str  = ""
    from_addr: str  = ""
    to_addrs:  list = field(default_factory=list)
    use_tls:   bool = True
    enabled:   bool = False


# ─────────────────────────────────────────────────────────
#  Default rules
# ─────────────────────────────────────────────────────────

DEFAULT_RULES = [
    AlertRule("r_cpu_crit",  "CPU Critical",     "cpu",      "gt", 90.0, "CRITICAL", 120),
    AlertRule("r_cpu_warn",  "CPU Warning",      "cpu",      "gt", 75.0, "WARNING",   60),
    AlertRule("r_mem_crit",  "Memory Critical",  "mem",      "gt", 90.0, "CRITICAL", 120),
    AlertRule("r_mem_warn",  "Memory Warning",   "mem",      "gt", 75.0, "WARNING",   60),
    AlertRule("r_disk_crit", "Disk Critical",    "disk",     "gt", 85.0, "CRITICAL",  90),
    AlertRule("r_ano_crit",  "Anomaly Critical", "ensemble", "gt",  0.8, "CRITICAL",  90),
    AlertRule("r_ano_warn",  "Anomaly Warning",  "ensemble", "gt",  0.5, "WARNING",   30),
    AlertRule("r_health",    "Health Degraded",  "health",   "lt", 60.0, "WARNING",   60),
]


# ─────────────────────────────────────────────────────────
#  Alert Engine
# ─────────────────────────────────────────────────────────

class AlertEngine:
    def __init__(self):
        self.rules:     dict[str, AlertRule]    = {r.rule_id: r for r in DEFAULT_RULES}
        self.webhooks:  dict[str, WebhookTarget] = {}
        self.email_cfg: Optional[EmailConfig]   = None
        self.history:   deque[FiredAlert]       = deque(maxlen=200)
        self._cooldowns: dict[str, float]       = {}
        self._http = httpx.AsyncClient(timeout=10.0)

        # Email alert cooldown — don't spam the inbox
        # One email per severity level per cooldown window
        self._email_cooldowns: dict[str, float] = {}
        self._email_cooldown_s = int(os.environ.get("ALERT_EMAIL_COOLDOWN_S", "300"))  # 5 min default

    # ── Evaluation ───────────────────────────────────────

    async def evaluate(self, metrics: dict):
        metric_map = {
            "cpu":      metrics.get("cpu_percent",   0),
            "mem":      metrics.get("memory",        0),
            "disk":     metrics.get("disk_percent",  0),
            "net":      metrics.get("network_percent",0),
            "health":   metrics.get("health_score",  100),
            "ensemble": metrics.get("anomaly_score", 0),
        }
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            value = metric_map.get(rule.metric)
            if value is None:
                continue
            if not self._check_op(value, rule.operator, rule.threshold):
                continue
            last = self._cooldowns.get(rule.rule_id, 0)
            if time.time() - last < rule.cooldown_s:
                continue

            self._cooldowns[rule.rule_id] = time.time()
            msg = rule.message_tpl.format(
                metric=rule.metric, value=value, threshold=rule.threshold
            )
            alert = FiredAlert(
                alert_id = str(uuid.uuid4())[:8],
                rule_id  = rule.rule_id,
                severity = rule.severity,
                message  = msg,
                metrics  = metrics,
                fired_at = time.time(),
            )
            self.history.appendleft(alert)
            await self._dispatch(alert)

    def _check_op(self, value, op, threshold) -> bool:
        return {
            "gt":  value >  threshold,
            "lt":  value <  threshold,
            "gte": value >= threshold,
            "lte": value <= threshold,
        }.get(op, False)

    # ── Dispatch ─────────────────────────────────────────

    async def _dispatch(self, alert: FiredAlert):
        tasks = []

        # Webhooks
        for wh in self.webhooks.values():
            if wh.enabled:
                tasks.append(self._send_webhook(wh, alert))

        # Legacy email config (from /alerts/email endpoint)
        if self.email_cfg and self.email_cfg.enabled:
            tasks.append(self._send_email_legacy(alert))

        # NEW: env-based email alerts via weekly_report.send_alert_email()
        # Fires on HIGH or CRITICAL if ALERT_EMAIL is set in .env
        if alert.severity in ("HIGH", "CRITICAL", "WARNING"):
            tasks.append(self._send_alert_email_env(alert))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    log.error("Alert dispatch error: %s", r)

    # ── NEW: env-based email alert ────────────────────────

    async def _send_alert_email_env(self, alert: FiredAlert):
        """
        Send alert email using ALERT_EMAIL from .env.
        Uses the rich HTML template from weekly_report.py.
        Respects a per-severity cooldown to avoid inbox flooding.
        """
        alert_email = os.environ.get("ALERT_EMAIL", "")
        if not alert_email:
            return  # not configured — skip silently

        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")
        if not smtp_user or not smtp_pass:
            return  # SMTP not configured — skip silently

        # Per-severity cooldown
        cooldown_key = f"email_{alert.severity}"
        last_sent    = self._email_cooldowns.get(cooldown_key, 0)
        if time.time() - last_sent < self._email_cooldown_s:
            log.debug("Email cooldown active for %s — skipping", alert.severity)
            return

        self._email_cooldowns[cooldown_key] = time.time()

        try:
            from backend.core.reports.weekly_report import send_alert_email

            # Build reason and actions from metrics
            metrics = alert.metrics
            cpu     = metrics.get("cpu_percent",   0)
            mem     = metrics.get("memory",        0)
            disk    = metrics.get("disk_percent",  0)
            anom    = metrics.get("anomaly_score", 0)

            reason_parts = []
            if cpu  > 75: reason_parts.append(f"CPU at {cpu:.1f}%")
            if mem  > 75: reason_parts.append(f"memory at {mem:.1f}%")
            if disk > 80: reason_parts.append(f"disk I/O at {disk:.1f}%")
            if anom > 0.5: reason_parts.append(f"anomaly score at {anom:.3f}")
            reason = (
                " and ".join(reason_parts) + " — threshold crossed."
                if reason_parts
                else alert.message
            )

            actions = metrics.get("actions", ["Check the CVIS dashboard for details."])
            if isinstance(actions, str):
                actions = [actions]
            if not actions:
                actions = ["Check the CVIS dashboard for details."]

            def _send():
                return send_alert_email(
                    severity = alert.severity,
                    message  = alert.message,
                    reason   = reason,
                    actions  = actions,
                    metrics  = metrics,
                )

            loop = asyncio.get_event_loop()
            ok   = await loop.run_in_executor(None, _send)
            if ok:
                alert.sent_to.append("email")
                log.info("Alert email sent → %s [%s]", alert_email, alert.severity)
            else:
                log.warning("Alert email failed — check SMTP config in .env")

        except Exception as e:
            log.error("Alert email error: %s", e)

    # ── Legacy email (from /alerts/email API config) ──────

    async def _send_email_legacy(self, alert: FiredAlert):
        """Legacy email using the EmailConfig dataclass set via API."""
        cfg = self.email_cfg
        if not cfg or not cfg.enabled:
            return
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            import smtplib

            subject = f"[CVIS {alert.severity}] {alert.message[:60]}"
            body    = self._build_email_html(alert)
            msg     = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = cfg.from_addr
            msg["To"]      = ", ".join(cfg.to_addrs)
            msg.attach(MIMEText(body, "html"))

            def _smtp():
                with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as s:
                    if cfg.use_tls:
                        s.starttls()
                    if cfg.username:
                        s.login(cfg.username, cfg.password)
                    s.sendmail(cfg.from_addr, cfg.to_addrs, msg.as_string())

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _smtp)
            alert.sent_to.append("email-legacy")
            log.info("Legacy email sent → %s", cfg.to_addrs)
        except Exception as e:
            log.error("Legacy email failed: %s", e)

    def _build_email_html(self, alert: FiredAlert) -> str:
        colour = {
            "CRITICAL": "#ff3350",
            "WARNING":  "#ffaa00",
            "HIGH":     "#fb923c",
            "INFO":     "#00c8ff",
        }.get(alert.severity, "#ccc")
        m = alert.metrics
        return f"""
        <div style="font-family:monospace;background:#060b18;color:#c8daf0;padding:24px;border-radius:8px">
          <h2 style="color:{colour};margin:0 0 12px">CVIS v9 · {alert.severity}</h2>
          <p style="color:#c8daf0;font-size:14px">{alert.message}</p>
          <table style="border-collapse:collapse;width:100%;margin-top:16px">
            <tr><td style="color:#3a6080;padding:4px 12px">CPU</td>
                <td style="color:#00c8ff;font-weight:700">{m.get('cpu_percent',0):.1f}%</td></tr>
            <tr><td style="color:#3a6080;padding:4px 12px">Memory</td>
                <td style="color:#4a7fff;font-weight:700">{m.get('memory',0):.1f}%</td></tr>
            <tr><td style="color:#3a6080;padding:4px 12px">Anomaly</td>
                <td style="color:#ff3350;font-weight:700">{m.get('anomaly_score',0):.4f}</td></tr>
            <tr><td style="color:#3a6080;padding:4px 12px">Health</td>
                <td style="color:#00ff9d;font-weight:700">{m.get('health_score',100):.1f}</td></tr>
          </table>
          <p style="color:#3a6080;font-size:11px;margin-top:16px">
            Alert ID: {alert.alert_id} · {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(alert.fired_at))}
          </p>
        </div>"""

    # ── Webhook ──────────────────────────────────────────

    async def _send_webhook(self, wh: WebhookTarget, alert: FiredAlert):
        payload = {
            "alert_id": alert.alert_id,
            "severity": alert.severity,
            "message":  alert.message,
            "metrics":  alert.metrics,
            "fired_at": alert.fired_at,
            "source":   "CVIS-v9",
        }
        headers = {"Content-Type": "application/json", "X-CVIS-Version": "9.0"}
        if wh.secret:
            import hmac, hashlib
            sig = hmac.new(
                wh.secret.encode(),
                json.dumps(payload).encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-CVIS-Signature"] = sig

        for attempt in range(wh.retries):
            try:
                resp = await self._http.post(wh.url, json=payload, headers=headers)
                resp.raise_for_status()
                wh.sent += 1
                alert.sent_to.append(wh.name)
                log.info("Webhook %s → %s [%d]", wh.name, wh.url, resp.status_code)
                return
            except Exception as e:
                log.warning("Webhook attempt %d/%d failed: %s", attempt+1, wh.retries, e)
                if attempt < wh.retries - 1:
                    await asyncio.sleep(2 ** attempt)
        wh.failed += 1

    # ── Rule management ──────────────────────────────────

    def add_rule(self, rule: AlertRule) -> AlertRule:
        self.rules[rule.rule_id] = rule
        return rule

    def update_rule(self, rule_id: str, **kwargs) -> Optional[AlertRule]:
        if rule_id not in self.rules:
            return None
        for k, v in kwargs.items():
            setattr(self.rules[rule_id], k, v)
        return self.rules[rule_id]

    def delete_rule(self, rule_id: str) -> bool:
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False

    # ── Webhook management ───────────────────────────────

    def add_webhook(self, url: str, name: str, secret: str = "") -> WebhookTarget:
        wh = WebhookTarget(id=str(uuid.uuid4())[:8], url=url, name=name, secret=secret)
        self.webhooks[wh.id] = wh
        log.info("Webhook added: %s → %s", name, url)
        return wh

    def remove_webhook(self, wh_id: str) -> bool:
        if wh_id in self.webhooks:
            del self.webhooks[wh_id]
            return True
        return False

    def configure_email(self, **kwargs) -> EmailConfig:
        self.email_cfg = EmailConfig(**kwargs)
        return self.email_cfg

    # ── Queries ──────────────────────────────────────────

    def get_history(self, limit: int = 50, severity: str = None) -> list:
        items = list(self.history)
        if severity:
            items = [a for a in items if a.severity == severity]
        return [asdict(a) for a in items[:limit]]

    def get_stats(self) -> dict:
        hist = list(self.history)
        alert_email_configured = bool(
            os.environ.get("ALERT_EMAIL") and
            os.environ.get("SMTP_USER") and
            os.environ.get("SMTP_PASS")
        )
        return {
            "total_alerts":        len(hist),
            "critical":            sum(1 for a in hist if a.severity == "CRITICAL"),
            "warning":             sum(1 for a in hist if a.severity in ("WARNING", "HIGH")),
            "info":                sum(1 for a in hist if a.severity == "INFO"),
            "webhooks_configured": len(self.webhooks),
            "email_configured":    bool(
                (self.email_cfg and self.email_cfg.enabled) or
                alert_email_configured
            ),
            "alert_email":         alert_email_configured,
            "rules_active":        sum(1 for r in self.rules.values() if r.enabled),
        }

    async def test_webhook(self, wh_id: str) -> bool:
        wh = self.webhooks.get(wh_id)
        if not wh:
            return False
        test_alert = FiredAlert(
            alert_id="TEST", rule_id="test", severity="INFO",
            message="CVIS v9 webhook test", metrics={}, fired_at=time.time(),
        )
        try:
            await self._send_webhook(wh, test_alert)
            return True
        except Exception:
            return False

    async def test_email(self) -> bool:
        """Test email config — call from /alerts/email/test endpoint."""
        try:
            from backend.core.reports.weekly_report import send_alert_email
            from datetime import datetime

            def _send():
                return send_alert_email(
                    severity = "INFO",
                    message  = "CVIS email alerts are working correctly.",
                    reason   = "This is a test alert sent from the CVIS dashboard.",
                    actions  = ["No action needed — this is just a test."],
                    metrics  = {
                        "cpu_percent":   25.0,
                        "memory":        45.0,
                        "disk_percent":  30.0,
                        "anomaly_score": 0.12,
                    },
                )

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _send)
        except Exception as e:
            log.error("Test email failed: %s", e)
            return False


# ─────────────────────────────────────────────────────────
#  Singleton
# ─────────────────────────────────────────────────────────

_engine: Optional[AlertEngine] = None

def get_alert_engine() -> AlertEngine:
    global _engine
    if _engine is None:
        _engine = AlertEngine()
    return _engine
