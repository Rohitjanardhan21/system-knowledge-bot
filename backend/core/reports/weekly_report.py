"""
CVIS Weekly Health Report
Generates a plain English summary of the past week's system health.
Runs every Monday morning via cron or scheduled task.

Usage:
    python3 weekly_report.py                    # print to console
    python3 weekly_report.py --email you@x.com  # send via email
    python3 weekly_report.py --server http://localhost:8000

Cron (every Monday 9am):
    0 9 * * 1 python3 /path/to/weekly_report.py
"""
import requests
import json
import os
import argparse
from datetime import datetime, timedelta

DEFAULT_SERVER = "http://localhost:8000"
DEFAULT_KEY    = "test123"

def fetch(server, key, path):
    try:
        req = urllib.request.Request(
            f"{server}{path}",
            headers={"X-API-Key": key} if key else {}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return _json.loads(r.read())
    except Exception:
        pass
    return None

def grade(score):
    if score >= 800: return "Excellent"
    if score >= 600: return "Good"
    if score >= 400: return "Fair"
    if score >= 200: return "Poor"
    return "Critical"

def trend_word(delta):
    if delta > 10:  return "significantly worse"
    if delta > 3:   return "slightly worse"
    if delta < -10: return "significantly better"
    if delta < -3:  return "slightly better"
    return "stable"

def generate_report(server: str, key: str) -> str:
    now   = datetime.now()
    week  = now.strftime("%B %d, %Y")
    lines = []

    # Fetch current data
    health  = fetch(server, key, "/health")
    dna     = fetch(server, key, "/cognitive/dna")
    fc      = fetch(server, key, "/cognitive/forecast")
    db_info = fetch(server, key, "/health")
    alerts  = fetch(server, key, "/alerts/history?limit=100")

    score    = health.get("health_credit_score", 0) if health else 0
    severity = health.get("severity", "UNKNOWN")    if health else "UNKNOWN"

    lines.append("=" * 56)
    lines.append(f"  CVIS Weekly Health Report — {week}")
    lines.append("=" * 56)
    lines.append("")

    # Overall score
    lines.append(f"  System Health Score: {score}/1000 ({grade(score)})")
    bar_filled = int(score / 1000 * 20)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    lines.append(f"  [{bar}]")
    lines.append("")

    # Alert summary
    if alerts:
        critical = [a for a in alerts if a.get("severity") == "CRITICAL"]
        warnings = [a for a in alerts if a.get("severity") == "WARNING"]
        lines.append(f"  Alerts This Week:")
        lines.append(f"  — Critical: {len(critical)}")
        lines.append(f"  — Warnings: {len(warnings)}")
        if len(critical) == 0:
            lines.append(f"  — No critical incidents. Clean week.")
        else:
            lines.append(f"  — Most recent: {critical[0].get('message','')}")
    lines.append("")

    # DNA summary
    if dna and dna.get("patterns", 0) > 0:
        prevented = dna.get("prevented", 0)
        patterns  = dna.get("patterns", 0)
        lines.append(f"  Failure DNA:")
        lines.append(f"  — {patterns} failure patterns learned")
        lines.append(f"  — {prevented} failures prevented this session")
        pattern_list = dna.get("pattern_list", [])
        for p in pattern_list[:3]:
            lines.append(f"  — {p['type']}: {p['accuracy']}% accurate, {p['lead_time']}min warning")
    lines.append("")

    # Forecast
    if fc:
        lines.append(f"  Next 60 Minutes:")
        lines.append(f"  — {fc.get('summary', 'No forecast available')}")
        peak = fc.get("peak_risk", "SAFE")
        lines.append(f"  — Peak risk: {peak}")
    lines.append("")

    # Recommendations
    lines.append("  Recommendations:")
    if score < 400:
        lines.append("  → System health is low. Check disk space and running processes.")
    if score < 600:
        lines.append("  → Consider restarting heavy processes to free memory.")
    if score >= 700:
        lines.append("  → System is healthy. No action needed.")
    if dna and dna.get("prevented", 0) > 0:
        lines.append(f"  → CVIS prevented {dna['prevented']} failures. Keep it running.")
    lines.append("")

    lines.append("  Open dashboard: http://localhost")
    lines.append("=" * 56)

    return "\n".join(lines)

def send_email(report: str, to_email: str):
    """Send report via email using smtplib."""
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_user:
        print("[CVIS] Set SMTP_USER and SMTP_PASS environment variables to send email")
        return False

    msg = MIMEText(report)
    msg["Subject"] = f"CVIS Weekly Health Report — {datetime.now().strftime('%B %d')}"
    msg["From"]    = smtp_user
    msg["To"]      = to_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        print(f"[CVIS] Report sent to {to_email}")
        return True
    except Exception as e:
        print(f"[CVIS] Email failed: {e}")
        return False

def save_report(report: str, path: str = "weekly_report.txt"):
    with open(path, "w") as f:
        f.write(report)
    print(f"[CVIS] Report saved to {path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CVIS Weekly Health Report")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--key",    default=DEFAULT_KEY)
    parser.add_argument("--email",  default=None, help="Send report to this email")
    parser.add_argument("--save",   default=None, help="Save report to this file")
    args = parser.parse_args()

    report = generate_report(args.server, args.key)
    print(report)

    if args.email:
        send_email(report, args.email)

    if args.save:
        save_report(report, args.save)
