"""
CVIS v9 — Alert Engine
Supports: webhooks (async HTTP POST), email (SMTP/TLS), Slack-compatible payloads.
Features: per-rule cooldowns, severity levels, alert history, rule management.
"""
import asyncio, smtplib, time, uuid, json, logging
from collections import deque
from dataclasses import dataclass, field, asdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx  # async HTTP for webhooks

log = logging.getLogger("cvis.alerts")

# ─────────────────────────────────────────────────────────
#  Data models
# ─────────────────────────────────────────────────────────
@dataclass
class AlertRule:
    rule_id:    str
    name:       str
    metric:     str    # "cpu" | "mem" | "disk" | "ano" | "ensemble" | "cascade"
    operator:   str    # "gt" | "lt" | "gte" | "lte"
    threshold:  float
    severity:   str    # "INFO" | "WARNING" | "CRITICAL"
    cooldown_s: int    = 60     # seconds between repeated alerts
    enabled:    bool   = True
    message_tpl: str  = "{metric} is {value:.2f} (threshold: {threshold})"


@dataclass
class FiredAlert:
    alert_id:   str
    rule_id:    str
    severity:   str
    message:    str
    metrics:    dict
    fired_at:   float
    resolved_at: Optional[float] = None
    sent_to:    list = field(default_factory=list)


@dataclass
class WebhookTarget:
    id:       str
    url:      str
    name:     str
    secret:   str    = ""    # optional HMAC header
    enabled:  bool   = True
    retries:  int    = 3
    sent:     int    = 0
    failed:   int    = 0


@dataclass
class EmailConfig:
    host:     str
    port:     int   = 587
    username: str   = ""
    password: str   = ""
    from_addr: str  = ""
    to_addrs:  list = field(default_factory=list)
    use_tls:  bool  = True
    enabled:  bool  = False


# ─────────────────────────────────────────────────────────
#  Built-in default rules
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
        self.rules:    dict[str, AlertRule]     = {r.rule_id: r for r in DEFAULT_RULES}
        self.webhooks: dict[str, WebhookTarget] = {}
        self.email_cfg: Optional[EmailConfig]  = None
        self.history:  deque[FiredAlert]        = deque(maxlen=200)
        self._cooldowns: dict[str, float]       = {}   # rule_id -> last_fired_ts
        self._http = httpx.AsyncClient(timeout=10.0)

    # ── evaluation ────────────────────────────────────────
    async def evaluate(self, metrics: dict):
        """
        Call every tick with a metrics dict:
        {cpu, mem, disk, net, health, ensemble_score, cascade_count, ...}
        """
        metric_map = {
            "cpu":      metrics.get("cpu_percent", 0),
            "mem":      metrics.get("memory", 0),
            "disk":     metrics.get("disk_percent", 0),
            "net":      metrics.get("network_percent", 0),
            "health":   metrics.get("health_score", 100),
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
            # Cooldown check
            last = self._cooldowns.get(rule.rule_id, 0)
            if time.time() - last < rule.cooldown_s:
                continue
            # Fire
            self._cooldowns[rule.rule_id] = time.time()
            msg = rule.message_tpl.format(
                metric=rule.metric, value=value, threshold=rule.threshold
            )
            alert = FiredAlert(
                alert_id  = str(uuid.uuid4())[:8],
                rule_id   = rule.rule_id,
                severity  = rule.severity,
                message   = msg,
                metrics   = metrics,
                fired_at  = time.time(),
            )
            self.history.appendleft(alert)
            await self._dispatch(alert)

    def _check_op(self, value, op, threshold) -> bool:
        ops = {"gt": value > threshold, "lt": value < threshold,
               "gte": value >= threshold, "lte": value <= threshold}
        return ops.get(op, False)

    # ── dispatch ──────────────────────────────────────────
    async def _dispatch(self, alert: FiredAlert):
        tasks = []
        for wh in self.webhooks.values():
            if wh.enabled:
                tasks.append(self._send_webhook(wh, alert))
        if self.email_cfg and self.email_cfg.enabled:
            tasks.append(self._send_email(alert))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    log.error("Alert dispatch error: %s", r)

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
            sig = hmac.new(wh.secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
            headers["X-CVIS-Signature"] = sig
        for attempt in range(wh.retries):
            try:
                resp = await self._http.post(wh.url, json=payload, headers=headers)
                resp.raise_for_status()
                wh.sent += 1
                alert.sent_to.append(wh.name)
                log.info("Webhook %s → %s  [%d]", wh.name, wh.url, resp.status_code)
                return
            except Exception as e:
                log.warning("Webhook attempt %d/%d failed: %s", attempt+1, wh.retries, e)
                if attempt < wh.retries - 1:
                    await asyncio.sleep(2 ** attempt)
        wh.failed += 1

    async def _send_email(self, alert: FiredAlert):
        cfg = self.email_cfg
        if not cfg or not cfg.enabled:
            return
        try:
            subject = f"[CVIS {alert.severity}] {alert.message[:60]}"
            body    = self._build_email_html(alert)
            msg = MIMEMultipart("alternative")
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
            alert.sent_to.append("email")
            log.info("Email sent → %s", cfg.to_addrs)
        except Exception as e:
            log.error("Email failed: %s", e)

    def _build_email_html(self, alert: FiredAlert) -> str:
        colour = {"CRITICAL": "#ff3350", "WARNING": "#ffaa00", "INFO": "#00c8ff"}.get(alert.severity, "#ccc")
        m = alert.metrics
        return f"""
        <div style="font-family:monospace;background:#060b18;color:#c8daf0;padding:24px;border-radius:8px">
          <h2 style="color:{colour};margin:0 0 12px">⚠ CVIS v9 · {alert.severity}</h2>
          <p style="color:#c8daf0;font-size:14px">{alert.message}</p>
          <table style="border-collapse:collapse;width:100%;margin-top:16px">
            <tr><td style="color:#3a6080;padding:4px 12px">CPU</td><td style="color:#00c8ff;font-weight:700">{m.get('cpu_percent',0):.1f}%</td></tr>
            <tr><td style="color:#3a6080;padding:4px 12px">Memory</td><td style="color:#4a7fff;font-weight:700">{m.get('memory',0):.1f}%</td></tr>
            <tr><td style="color:#3a6080;padding:4px 12px">Anomaly</td><td style="color:#ff3350;font-weight:700">{m.get('anomaly_score',0):.4f}</td></tr>
            <tr><td style="color:#3a6080;padding:4px 12px">Health</td><td style="color:#00ff9d;font-weight:700">{m.get('health_score',100):.1f}%</td></tr>
          </table>
          <p style="color:#3a6080;font-size:11px;margin-top:16px">Alert ID: {alert.alert_id} · {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(alert.fired_at))}</p>
        </div>"""

    # ── rule management ───────────────────────────────────
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

    # ── webhook management ────────────────────────────────
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

    # ── queries ───────────────────────────────────────────
    def get_history(self, limit: int = 50, severity: str = None) -> list:
        items = list(self.history)
        if severity:
            items = [a for a in items if a.severity == severity]
        return [asdict(a) for a in items[:limit]]

    def get_stats(self) -> dict:
        hist = list(self.history)
        return {
            "total_alerts": len(hist),
            "critical": sum(1 for a in hist if a.severity == "CRITICAL"),
            "warning":  sum(1 for a in hist if a.severity == "WARNING"),
            "info":     sum(1 for a in hist if a.severity == "INFO"),
            "webhooks_configured": len(self.webhooks),
            "email_configured": bool(self.email_cfg and self.email_cfg.enabled),
            "rules_active": sum(1 for r in self.rules.values() if r.enabled),
        }

    async def test_webhook(self, wh_id: str) -> bool:
        wh = self.webhooks.get(wh_id)
        if not wh:
            return False
        test_alert = FiredAlert(
            alert_id="TEST", rule_id="test", severity="INFO",
            message="CVIS v9 webhook test", metrics={}, fired_at=time.time()
        )
        try:
            await self._send_webhook(wh, test_alert)
            return True
        except Exception:
            return False


# singleton
_engine: Optional[AlertEngine] = None

def get_alert_engine() -> AlertEngine:
    global _engine
    if _engine is None:
        _engine = AlertEngine()
    return _engine
