"""
CVIS Weekly Health Report + Alert Email Engine
===============================================
Generates a plain-English summary of the past week's system health.
Also used by the alert engine to send real-time CRITICAL/HIGH alerts.

Usage:
    python3 weekly_report.py                         # print to console
    python3 weekly_report.py --email you@gmail.com   # send weekly report
    python3 weekly_report.py --server http://localhost:8000

Cron (every Monday 9am):
    0 9 * * 1 python3 /path/to/weekly_report.py --email you@gmail.com

Environment variables required for email:
    SMTP_HOST      smtp.gmail.com
    SMTP_PORT      587
    SMTP_USER      you@gmail.com
    SMTP_PASS      your-app-password   (Gmail App Password, not login password)
    ALERT_EMAIL    you@gmail.com       (where to send alerts)
    ALERT_MIN_SEVERITY  HIGH           (minimum severity to email: HIGH or CRITICAL)
"""

import os
import smtplib
import urllib.request
import json as _json
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

log = logging.getLogger("cvis.email")

DEFAULT_SERVER = "http://localhost:8000"
DEFAULT_KEY    = os.environ.get("CVIS_API_KEY", "test123")


# ─────────────────────────────────────────────────────────
#  HTTP helper
# ─────────────────────────────────────────────────────────

def _fetch(server: str, key: str, path: str) -> Optional[dict]:
    try:
        req = urllib.request.Request(
            f"{server}{path}",
            headers={"X-API-Key": key} if key else {},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return _json.loads(r.read())
    except Exception:
        return None


# ─────────────────────────────────────────────────────────
#  Formatting helpers
# ─────────────────────────────────────────────────────────

def _grade(score: int) -> str:
    if score >= 800: return "Excellent"
    if score >= 600: return "Good"
    if score >= 400: return "Fair"
    if score >= 200: return "Poor"
    return "Critical"

def _grade_explain(score: int) -> str:
    if score >= 800: return "Your system is running well. No action needed."
    if score >= 600: return "Your system is in decent shape with minor areas to watch."
    if score >= 400: return "Your system is under some stress. A few things need attention."
    if score >= 200: return "Your system health is poor. Intervention recommended."
    return "Your system is in a critical state. Immediate action required."

def _severity_explain(severity: str) -> str:
    return {
        "CRITICAL": "One or more metrics are at dangerous levels. Act now.",
        "HIGH":     "Significant anomalies detected. Keep a close eye on this.",
        "MEDIUM":   "Mild anomalies present. Worth monitoring.",
        "LOW":      "Everything looks normal. No action needed.",
    }.get(severity, "Status unknown.")

def _risk_explain(risk: str) -> str:
    return {
        "CRITICAL": "system may become unresponsive or crash",
        "HIGH":     "significant performance degradation likely",
        "ELEVATED": "mild slowdowns possible",
        "SAFE":     "no issues expected",
    }.get(risk, "unknown risk")

def _bar(score: int, width: int = 20) -> str:
    filled = int(score / 1000 * width)
    return "█" * filled + "░" * (width - filled)


# ─────────────────────────────────────────────────────────
#  Report generator — real data, real explanations
# ─────────────────────────────────────────────────────────

def generate_report(server: str = DEFAULT_SERVER, key: str = DEFAULT_KEY) -> str:
    now  = datetime.now()
    week = now.strftime("%B %d, %Y at %I:%M %p")

    # Fetch all data
    health  = _fetch(server, key, "/health/full")
    dna     = _fetch(server, key, "/cognitive/dna")
    fc      = _fetch(server, key, "/cognitive/forecast")
    preds   = _fetch(server, key, "/cognitive/predictions")
    pm      = _fetch(server, key, "/cognitive/premortem")
    alerts  = _fetch(server, key, "/alerts/history?limit=100")
    os_stat = _fetch(server, key, "/os/status")
    hs      = _fetch(server, key, "/cognitive/health-score")

    lines = []

    # ── Header ──────────────────────────────────────────
    lines += [
        "=" * 60,
        f"  CVIS Weekly Health Report",
        f"  Generated: {week}",
        "=" * 60,
        "",
    ]

    # ── Health Score ─────────────────────────────────────
    score    = (hs or health or {}).get("score") or (health or {}).get("health_credit_score") or 0
    grade    = _grade(int(score))
    severity = (health or {}).get("severity", "UNKNOWN")

    lines += [
        "  SYSTEM HEALTH",
        "  " + "-" * 40,
        f"  Score:    {score}/1000  ({grade})",
        f"  [{_bar(int(score))}]",
        f"  Status:   {severity}",
        f"  {_grade_explain(int(score))}",
        f"  {_severity_explain(severity)}",
        "",
    ]

    # ── Current Metrics ──────────────────────────────────
    if os_stat:
        cpu   = os_stat.get("cpu_percent",    0)
        mem   = os_stat.get("memory",         0)
        disk  = os_stat.get("disk_percent",   0)
        anom  = (health or {}).get("anomaly_score", os_stat.get("ensemble_score", 0))

        def _metric_note(val, warn, crit, unit="%"):
            if val >= crit: return f"⚠ CRITICAL ({val:.1f}{unit})"
            if val >= warn: return f"▲ Elevated ({val:.1f}{unit})"
            return f"✓ Normal ({val:.1f}{unit})"

        lines += [
            "  CURRENT METRICS",
            "  " + "-" * 40,
            f"  CPU:          {_metric_note(cpu,  70, 85)}",
            f"  Memory:       {_metric_note(mem,  75, 85)}",
            f"  Disk I/O:     {_metric_note(disk, 70, 85)}",
            f"  Anomaly:      {_metric_note(anom, 0.4, 0.7, '')}",
            "",
        ]

        # Add plain-English explanation for elevated metrics
        explanations = []
        if cpu >= 85:
            explanations.append(f"CPU is critically high at {cpu:.1f}%. Check for runaway processes.")
        elif cpu >= 70:
            explanations.append(f"CPU is elevated at {cpu:.1f}%. Monitor for sustained spikes.")
        if mem >= 85:
            explanations.append(f"Memory is critically high at {mem:.1f}%. Consider closing heavy applications.")
        elif mem >= 75:
            explanations.append(f"Memory pressure at {mem:.1f}%. Watch for upward trends.")
        if anom >= 0.7:
            explanations.append(f"ML anomaly score is high at {anom:.2f}. Unusual behaviour detected.")
        elif anom >= 0.4:
            explanations.append(f"ML anomaly score is mildly elevated at {anom:.2f}. Worth monitoring.")

        if explanations:
            lines.append("  What this means:")
            for ex in explanations:
                lines.append(f"  → {ex}")
            lines.append("")

    # ── Active Predictions ───────────────────────────────
    if preds:
        lines += [
            "  ACTIVE PREDICTIONS",
            "  " + "-" * 40,
        ]
        for p in preds[:3]:
            eta  = int(p.get("eta_minutes", 0))
            conf = int(p.get("confidence",  0))
            sev  = p.get("severity", "")
            msg  = p.get("message",  "")
            act  = p.get("action",   "")
            lines.append(f"  [{sev}] {p.get('type','?')} — {eta} minutes away ({conf}% confidence)")
            lines.append(f"  {msg}")
            lines.append(f"  → What to do: {act}")
            lines.append("")
    else:
        lines += [
            "  ACTIVE PREDICTIONS",
            "  " + "-" * 40,
            "  ✓ No active failure predictions. System looks stable.",
            "",
        ]

    # ── Failure DNA ──────────────────────────────────────
    if dna and dna.get("patterns", 0) > 0:
        prevented = dna.get("prevented", 0)
        patterns  = dna.get("patterns",  0)
        lines += [
            "  FAILURE DNA",
            "  " + "-" * 40,
            f"  {patterns} failure patterns learned from this machine.",
            f"  {prevented} failures prevented this session.",
            "",
            "  Pattern breakdown:",
        ]
        for p in (dna.get("pattern_list") or [])[:5]:
            trusted = "✓ Trusted" if p.get("trustworthy") else "⚠ Learning"
            lines.append(
                f"  {p['type']:12} | {p['accuracy']:5.1f}% accurate | "
                f"{p['lead_time']}min warning | {trusted}"
            )
            if p.get("description"):
                lines.append(f"               {p['description']}")
        lines.append("")

        # Explanation
        if prevented > 0:
            lines.append(
                f"  CVIS caught {prevented} failure(s) before they happened by recognising "
                f"early warning patterns specific to this machine."
            )
            lines.append("")

    # ── Alert History ────────────────────────────────────
    if alerts:
        critical = [a for a in alerts if a.get("severity") == "CRITICAL"]
        high     = [a for a in alerts if a.get("severity") in ("HIGH", "WARNING")]
        lines += [
            "  ALERT HISTORY (last 100)",
            "  " + "-" * 40,
            f"  Critical alerts:  {len(critical)}",
            f"  High alerts:      {len(high)}",
            f"  Total alerts:     {len(alerts)}",
            "",
        ]
        if critical:
            lines.append("  Most recent critical alerts:")
            for a in critical[:3]:
                ts  = datetime.fromtimestamp(a.get("fired_at", 0)).strftime("%b %d %I:%M %p")
                lines.append(f"  [{ts}] {a.get('message','')}")
            lines.append("")
        if len(critical) == 0:
            lines.append("  ✓ No critical incidents. Clean week.")
            lines.append("")

    # ── 60-Minute Forecast ───────────────────────────────
    if fc:
        direction = fc.get("direction",     "UNKNOWN")
        peak      = fc.get("peak_risk",     "SAFE")
        summary   = fc.get("summary",       "No forecast available")
        conf      = fc.get("confidence_label", f"{int((fc.get('confidence',0))*100)}% confidence")
        first_risk= fc.get("first_risk_at")
        watch     = fc.get("what_to_watch", [])

        lines += [
            "  60-MINUTE FORECAST",
            "  " + "-" * 40,
            f"  Direction:    {direction}",
            f"  Peak risk:    {peak} — {_risk_explain(peak)}",
            f"  Confidence:   {conf}",
            f"  Summary:      {summary}",
        ]
        if first_risk:
            lines.append(f"  First risk at: +{first_risk} minutes")
        if watch:
            lines.append("")
            lines.append("  What to watch:")
            for w in watch[:2]:
                lines.append(f"  → {w}")
        lines.append("")

    # ── Pre-Mortem ───────────────────────────────────────
    if pm and not pm.get("safe") and pm.get("threats"):
        lines += [
            "  30-DAY FAILURE FORECAST",
            "  " + "-" * 40,
            f"  {pm.get('summary', '')}",
            "",
            "  Threats identified:",
        ]
        for t in (pm.get("threats") or [])[:3]:
            prob = t.get("probability", 0)
            days = t.get("days_until")
            days_str = f"~{int(days)} days" if days else "no fixed timeline"
            lines.append(f"  [{prob:.0f}%] {t['failure_type']} — {days_str}")
            lines.append(f"  {t.get('headline','')}")
            lines.append(f"  → {t.get('recommendation','')}")
            lines.append("")
    elif pm and pm.get("safe"):
        lines += [
            "  30-DAY FAILURE FORECAST",
            "  " + "-" * 40,
            "  ✓ No critical threats identified in the next 30 days.",
            "",
        ]

    # ── Recommendations ──────────────────────────────────
    recs = []
    score_int = int(score)
    if score_int < 400:
        recs.append("System health is low. Check disk space, close heavy processes, and restart if needed.")
    elif score_int < 600:
        recs.append("Health is fair. Monitor memory usage and avoid running multiple heavy tasks simultaneously.")
    else:
        recs.append("System is healthy. Keep CVIS running to continue building failure DNA.")

    if dna and dna.get("prevented", 0) > 0:
        recs.append(f"CVIS prevented {dna['prevented']} failure(s) this session. Keep it running in the background.")

    if preds:
        recs.append("Active predictions are firing. Review them in the dashboard and take the suggested actions.")

    lines += [
        "  RECOMMENDATIONS",
        "  " + "-" * 40,
    ]
    for r in recs:
        lines.append(f"  → {r}")
    lines.append("")

    # ── Footer ───────────────────────────────────────────
    lines += [
        "  Dashboard: http://localhost:8000",
        "  Live demo: https://cvis-os-latest.onrender.com",
        "=" * 60,
        "  This report was generated automatically by CVIS.",
        "  All data is from your local machine — nothing sent to the cloud.",
        "=" * 60,
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
#  Email sender — used for both weekly reports and alerts
# ─────────────────────────────────────────────────────────

def send_email(
    subject:  str,
    body:     str,
    to_email: str,
    html_body: Optional[str] = None,
) -> bool:
    """
    Send an email via SMTP.
    Used for weekly reports and real-time alerts.
    Reads SMTP config from environment variables.
    """
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        log.warning(
            "Email not configured — set SMTP_USER and SMTP_PASS in .env to enable alerts"
        )
        return False

    try:
        if html_body:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body,      "plain"))
            msg.attach(MIMEText(html_body, "html"))
        else:
            msg = MIMEText(body, "plain")

        msg["Subject"] = subject
        msg["From"]    = f"CVIS Alert <{smtp_user}>"
        msg["To"]      = to_email

        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.ehlo()
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)

        log.info("Email sent to %s: %s", to_email, subject)
        return True

    except Exception as e:
        log.error("Email failed: %s", e)
        return False


# ─────────────────────────────────────────────────────────
#  Alert email — called by alert_engine when severity fires
# ─────────────────────────────────────────────────────────

def send_alert_email(
    severity:   str,
    message:    str,
    reason:     str,
    actions:    list,
    metrics:    dict,
    server:     str = DEFAULT_SERVER,
    key:        str = DEFAULT_KEY,
) -> bool:
    """
    Send a real-time alert email when CRITICAL or HIGH severity fires.
    Called from the alert engine — not from the weekly report.
    """
    to_email    = os.environ.get("ALERT_EMAIL", "")
    min_sev     = os.environ.get("ALERT_MIN_SEVERITY", "HIGH")

    if not to_email:
        return False

    # Only send if severity meets the minimum threshold
    sev_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    if sev_rank.get(severity, 0) < sev_rank.get(min_sev, 2):
        return False

    now     = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    cpu     = metrics.get("cpu_percent",  0)
    mem     = metrics.get("memory",       0)
    disk    = metrics.get("disk_percent", 0)
    anomaly = metrics.get("anomaly_score",0)

    sev_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}.get(severity, "⚪")

    # Plain text body
    plain = f"""
CVIS Alert — {severity}
{now}

{sev_emoji} {message}

What's happening:
{reason}

Current metrics:
  CPU:     {cpu:.1f}%
  Memory:  {mem:.1f}%
  Disk:    {disk:.1f}%
  Anomaly: {anomaly:.3f}

What to do:
{chr(10).join(f'  → {a}' for a in actions)}

Open dashboard: {server}

—
This alert was sent automatically by CVIS.
All data is from your local machine.
""".strip()

    # HTML body — cleaner for email clients
    action_html = "".join(f"<li>{a}</li>" for a in actions)
    sev_color   = {"CRITICAL": "#f87171", "HIGH": "#fb923c", "MEDIUM": "#fbbf24"}.get(severity, "#34d399")

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f5;padding:20px;margin:0">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1)">

    <!-- Header -->
    <div style="background:{sev_color};padding:20px 28px">
      <div style="color:#fff;font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px">CVIS Alert</div>
      <div style="color:#fff;font-size:22px;font-weight:700">{sev_emoji} {severity}</div>
      <div style="color:rgba(255,255,255,.8);font-size:12px;margin-top:4px">{now}</div>
    </div>

    <!-- Body -->
    <div style="padding:24px 28px">
      <p style="font-size:16px;font-weight:600;color:#111;margin:0 0 8px">{message}</p>
      <p style="font-size:13px;color:#555;margin:0 0 20px;line-height:1.6">{reason}</p>

      <!-- Metrics -->
      <div style="background:#f8f8f8;border-radius:6px;padding:14px 16px;margin-bottom:20px">
        <div style="font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#888;margin-bottom:10px">Current Metrics</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div><span style="color:#888;font-size:12px">CPU</span><br><span style="font-size:18px;font-weight:600;color:#111">{cpu:.1f}%</span></div>
          <div><span style="color:#888;font-size:12px">Memory</span><br><span style="font-size:18px;font-weight:600;color:#111">{mem:.1f}%</span></div>
          <div><span style="color:#888;font-size:12px">Disk I/O</span><br><span style="font-size:18px;font-weight:600;color:#111">{disk:.1f}%</span></div>
          <div><span style="color:#888;font-size:12px">Anomaly</span><br><span style="font-size:18px;font-weight:600;color:#111">{anomaly:.3f}</span></div>
        </div>
      </div>

      <!-- Actions -->
      <div style="margin-bottom:20px">
        <div style="font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#888;margin-bottom:8px">What To Do</div>
        <ul style="margin:0;padding:0 0 0 18px;color:#333;font-size:13px;line-height:1.8">{action_html}</ul>
      </div>

      <!-- CTA -->
      <a href="{server}" style="display:inline-block;background:#7c6af7;color:#fff;text-decoration:none;padding:10px 20px;border-radius:6px;font-size:13px;font-weight:600">
        Open Dashboard →
      </a>
    </div>

    <!-- Footer -->
    <div style="padding:14px 28px;background:#f8f8f8;border-top:1px solid #eee">
      <p style="margin:0;font-size:11px;color:#aaa">
        Sent by CVIS — running locally on your machine. No data left your network.
      </p>
    </div>

  </div>
</body>
</html>
""".strip()

    subject = f"CVIS {sev_emoji} {severity} Alert — {message[:60]}"
    return send_email(subject, plain, to_email, html_body=html)


# ─────────────────────────────────────────────────────────
#  Weekly report email
# ─────────────────────────────────────────────────────────

def send_weekly_report_email(
    to_email: str,
    server:   str = DEFAULT_SERVER,
    key:      str = DEFAULT_KEY,
) -> bool:
    report  = generate_report(server, key)
    subject = f"CVIS Weekly Health Report — {datetime.now().strftime('%B %d, %Y')}"
    return send_email(subject, report, to_email)


# ─────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CVIS Weekly Health Report")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="CVIS backend URL")
    parser.add_argument("--key",    default=DEFAULT_KEY,    help="API key")
    parser.add_argument("--email",  default=None,           help="Send report to this email")
    parser.add_argument("--save",   default=None,           help="Save report to this file")
    args = parser.parse_args()

    report = generate_report(args.server, args.key)
    print(report)

    if args.email:
        ok = send_weekly_report_email(args.email, args.server, args.key)
        if not ok:
            print("\n[CVIS] Email not sent — check SMTP_USER, SMTP_PASS, SMTP_HOST in .env")

    if args.save:
        with open(args.save, "w") as f:
            f.write(report)
        print(f"\n[CVIS] Report saved to {args.save}")
