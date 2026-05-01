"""
CVIS Tray Agent
Runs silently in the system tray.
Monitors your machine, sends OS notifications when something matters.
No browser needed. Like a smoke detector — you forget it's there until it saves you.

Usage:
    python3 tray_agent.py
    python3 tray_agent.py --server http://localhost:8000 --key test123

Requirements:
    pip install pystray pillow plyer requests
"""
import threading
import time
import sys
import os
import argparse
import requests
from datetime import datetime

# ── Config ────────────────────────────────────────────────
DEFAULT_SERVER  = "http://localhost:8000"
DEFAULT_KEY     = "test123"
POLL_INTERVAL   = 10   # seconds between checks
NOTIFY_COOLDOWN = 300  # seconds between same-type notifications

# ── Notification cooldown tracker ─────────────────────────
_last_notified: dict = {}

def should_notify(key: str) -> bool:
    now = time.time()
    if now - _last_notified.get(key, 0) > NOTIFY_COOLDOWN:
        _last_notified[key] = now
        return True
    return False

# ── OS notification ───────────────────────────────────────
def notify(title: str, message: str, urgency: str = "normal"):
    """Send OS-native notification."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="CVIS",
            timeout=10,
        )
        return
    except Exception:
        pass

    # Fallback per OS
    import platform
    OS = platform.system()
    try:
        if OS == "Darwin":
            os.system(f'osascript -e \'display notification "{message}" with title "{title}"\'')
        elif OS == "Linux":
            os.system(f'notify-send "{title}" "{message}" -t 8000')
        else:
            print(f"[CVIS] {title}: {message}")
    except Exception:
        print(f"[CVIS] {title}: {message}")

# ── Health check ──────────────────────────────────────────
def check_health(server: str, key: str) -> dict | None:
    try:
        r = requests.get(
            f"{server}/health",
            headers={"X-API-Key": key},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def check_prediction(server: str, key: str) -> dict | None:
    try:
        r = requests.get(
            f"{server}/cognitive/predictions",
            headers={"X-API-Key": key},
            timeout=5,
        )
        if r.status_code == 200:
            preds = r.json()
            for p in preds:
                if not p.get("acknowledged"):
                    return p
    except Exception:
        pass
    return None

# ── Main monitoring loop ──────────────────────────────────
def monitor_loop(server: str, key: str, icon=None):
    print(f"[CVIS] Monitoring {server}")
    consecutive_failures = 0

    while True:
        try:
            health = check_health(server, key)

            if health is None:
                consecutive_failures += 1
                if consecutive_failures == 3:
                    notify("CVIS — Connection Lost", "Cannot reach CVIS backend. Check if it's running.")
                time.sleep(POLL_INTERVAL)
                continue

            consecutive_failures = 0
            severity   = health.get("severity", "LOW")
            score      = health.get("health_credit_score")
            reason     = health.get("reason", "")
            actions    = health.get("actions", [])

            # Update tray tooltip
            if icon:
                score_str = f"{score}/1000" if score else "—"
                icon.title = f"CVIS — {severity} | Health {score_str}"

            # Notify on CRITICAL
            if severity == "CRITICAL" and should_notify("CRITICAL"):
                action = actions[0] if actions else "Check CVIS dashboard"
                notify(
                    "⚠️ CVIS — CRITICAL",
                    f"{reason}\n→ {action}",
                    urgency="critical",
                )

            # Notify on HIGH
            elif severity == "HIGH" and should_notify("HIGH"):
                notify(
                    "🔶 CVIS — HIGH",
                    f"{reason}",
                    urgency="normal",
                )

            # Check for active prediction
            pred = check_prediction(server, key)
            if pred and should_notify(f"pred_{pred.get('id')}"):
                eta  = round(pred.get("eta_min", 0))
                ptype = pred.get("type", "UNKNOWN")
                msg   = pred.get("message", "")
                notify(
                    f"🔮 CVIS — {ptype} in {eta} minutes",
                    f"{msg}\nOpen CVIS to act.",
                    urgency="critical",
                )

            # Low score warning
            if score and score < 400 and should_notify("low_score"):
                notify(
                    "CVIS — Health Low",
                    f"System health at {score}/1000. Open CVIS for details.",
                )

        except Exception as e:
            print(f"[CVIS] Monitor error: {e}")

        time.sleep(POLL_INTERVAL)

# ── System tray ───────────────────────────────────────────
def create_tray(server: str, key: str):
    try:
        import pystray
        from PIL import Image, ImageDraw

        # Draw a simple icon
        def make_icon(color="#7c6af7"):
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([8, 8, 56, 56], fill=color)
            draw.text((20, 18), "CV", fill="white")
            return img

        icon_img = make_icon()

        def open_dashboard(icon, item):
            import webbrowser
            webbrowser.open(f"{server}")

        def quit_app(icon, item):
            icon.stop()
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", open_dashboard, default=True),
            pystray.MenuItem("Quit CVIS", quit_app),
        )

        icon = pystray.Icon("CVIS", icon_img, "CVIS — Starting…", menu)

        # Start monitor in background thread
        t = threading.Thread(
            target=monitor_loop,
            args=(server, key, icon),
            daemon=True,
        )
        t.start()

        print("[CVIS] Tray agent running. Right-click tray icon to open dashboard or quit.")
        icon.run()

    except ImportError:
        print("[CVIS] pystray/Pillow not installed — running in console mode")
        print("[CVIS] Install with: pip install pystray pillow")
        monitor_loop(server, key, icon=None)

# ── Entry point ───────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CVIS Silent Tray Agent")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--key",    default=DEFAULT_KEY)
    parser.add_argument("--console", action="store_true",
                        help="Run in console mode without tray icon")
    args = parser.parse_args()

    notify("CVIS Started", f"Monitoring {args.server} silently in background.")

    if args.console:
        monitor_loop(args.server, args.key, icon=None)
    else:
        create_tray(args.server, args.key)
