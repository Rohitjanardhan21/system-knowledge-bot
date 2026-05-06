"""
CVIS Desktop App
================
Native application window + system tray integration.
Behaves like ArmouryCrate — window when you want it, tray when you don't.

Double-click CVIS.exe:
  → Backend starts silently
  → Native window opens showing the full dashboard
  → Minimising goes to tray
  → Tray icon shows badge on CRITICAL alerts
  → Windows notifications fire on predictions

Build:
  python -m PyInstaller build_app.spec --clean --noconfirm
"""

import sys
import os
import threading
import time
import json
import logging
import urllib.request
import urllib.error

# ── Suppress console window on Windows ───────────────────
if sys.platform == "win32":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("cvis_app.log"), logging.StreamHandler()],
)
log = logging.getLogger("cvis.app")

# ── Constants ─────────────────────────────────────────────
BACKEND_URL  = "http://127.0.0.1:8000"
API_KEY      = "test123"
WINDOW_W     = 1440
WINDOW_H     = 900
MIN_W        = 1024
MIN_H        = 700
POLL_SECONDS = 10          # how often tray checks for alerts
APP_TITLE    = "CVIS — Cognitive AIOps"

# ── State shared between threads ─────────────────────────
_window       = None       # pywebview window reference
_tray         = None       # pystray icon reference
_last_sev     = "LOW"
_backend_up   = False
_shutdown     = False


# ─────────────────────────────────────────────────────────
#  Backend launcher
# ─────────────────────────────────────────────────────────

def _start_backend():
    """Start the FastAPI backend in a daemon thread."""
    global _backend_up
    try:
        # Ensure data directories exist
        os.makedirs("data",           exist_ok=True)
        os.makedirs("logs",           exist_ok=True)
        os.makedirs("model_versions", exist_ok=True)

        # Copy .env.example → .env if .env doesn't exist
        if not os.path.exists(".env") and os.path.exists(".env.example"):
            import shutil
            shutil.copy(".env.example", ".env")

        import uvicorn
        from backend.main import app as fastapi_app

        log.info("Starting CVIS backend on %s", BACKEND_URL)
        uvicorn.run(
            fastapi_app,
            host="127.0.0.1",
            port=8000,
            log_level="warning",
            access_log=False,
        )
    except Exception as e:
        log.error("Backend failed to start: %s", e)


def _wait_for_backend(timeout: int = 30) -> bool:
    """Poll /health until the backend responds or timeout."""
    global _backend_up
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                f"{BACKEND_URL}/health",
                headers={"X-API-Key": API_KEY},
            )
            with urllib.request.urlopen(req, timeout=2):
                _backend_up = True
                log.info("Backend ready")
                return True
        except Exception:
            time.sleep(0.5)
    log.error("Backend did not start within %ds", timeout)
    return False


# ─────────────────────────────────────────────────────────
#  Alert poller — fires Windows notifications
# ─────────────────────────────────────────────────────────

def _fetch_json(path: str):
    try:
        req = urllib.request.Request(
            f"{BACKEND_URL}{path}",
            headers={"X-API-Key": API_KEY},
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _send_notification(title: str, message: str):
    """Send a Windows toast notification."""
    if sys.platform != "win32":
        return
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(
            title, message,
            duration=8,
            threaded=True,
        )
    except ImportError:
        # Fallback: use PowerShell notification
        try:
            import subprocess
            ps = (
                f"Add-Type -AssemblyName System.Windows.Forms;"
                f"$n = New-Object System.Windows.Forms.NotifyIcon;"
                f"$n.Icon = [System.Drawing.SystemIcons]::Information;"
                f"$n.Visible = $true;"
                f"$n.ShowBalloonTip(8000, '{title}', '{message}', "
                f"[System.Windows.Forms.ToolTipIcon]::Warning);"
                f"Start-Sleep -s 9; $n.Dispose()"
            )
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        except Exception as e:
            log.warning("Notification failed: %s", e)


_last_pred_id  = None
_last_notif_at = 0.0

def _alert_poller():
    """Background thread — polls backend, fires notifications, updates tray icon."""
    global _last_sev, _last_pred_id, _last_notif_at

    while not _shutdown:
        if not _backend_up:
            time.sleep(2)
            continue

        try:
            # Check active prediction
            preds = _fetch_json("/cognitive/predictions")
            if preds and len(preds) > 0:
                pred = preds[0]
                pid  = pred.get("id")
                sev  = pred.get("severity", "LOW")
                eta  = int(pred.get("eta_minutes", 0))
                msg  = pred.get("message", "")
                conf = int(pred.get("confidence", 0))

                # Fire notification if new prediction
                now = time.time()
                if pid != _last_pred_id and now - _last_notif_at > 60:
                    _last_pred_id  = pid
                    _last_notif_at = now
                    _send_notification(
                        f"⚠ CVIS — {sev} Alert",
                        f"{msg}\nExpected in ~{eta} min ({conf}% confidence)",
                    )

                _last_sev = sev

            else:
                # Check anomaly severity from health endpoint
                health = _fetch_json("/health")
                if health:
                    _last_sev = health.get("severity", "LOW")

            # Update tray icon colour
            _update_tray_icon()

        except Exception as e:
            log.debug("Poller error: %s", e)

        time.sleep(POLL_SECONDS)


# ─────────────────────────────────────────────────────────
#  Tray icon
# ─────────────────────────────────────────────────────────

def _make_tray_image(severity: str = "LOW"):
    """
    Generate a coloured circle icon for the tray.
    Green = LOW, Yellow = MEDIUM, Orange = HIGH, Red = CRITICAL.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    size   = 64
    img    = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(img)
    colors = {
        "LOW":      "#34d399",
        "MEDIUM":   "#fbbf24",
        "HIGH":     "#fb923c",
        "CRITICAL": "#f87171",
    }
    c = colors.get(severity, "#34d399")

    # Outer ring
    draw.ellipse([2, 2, size-2, size-2], outline=c, width=4)
    # Inner fill — semi-transparent
    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    draw.ellipse([8, 8, size-8, size-8], fill=(r, g, b, 120))

    # CRITICAL: add exclamation mark
    if severity == "CRITICAL":
        draw.rectangle([30, 14, 34, 36], fill=(r, g, b, 255))
        draw.ellipse([30, 42, 34, 46],   fill=(r, g, b, 255))

    return img


def _update_tray_icon():
    """Swap the tray icon colour to match current severity."""
    global _tray
    if _tray is None:
        return
    try:
        img = _make_tray_image(_last_sev)
        if img:
            _tray.icon = img
    except Exception:
        pass


def _show_window():
    global _window
    if _window:
        try:
            _window.show()
            _window.restore()
        except Exception:
            pass


def _hide_window():
    global _window
    if _window:
        try:
            _window.hide()
        except Exception:
            pass


def _quit_app(icon=None, item=None):
    global _shutdown
    _shutdown = True
    if _tray:
        try:
            _tray.stop()
        except Exception:
            pass
    if _window:
        try:
            _window.destroy()
        except Exception:
            pass
    sys.exit(0)


def _build_tray_menu():
    try:
        import pystray
        from pystray import MenuItem as Item, Menu

        return Menu(
            Item("Open CVIS",    lambda icon, item: _show_window(), default=True),
            Item("Dashboard",    lambda icon, item: _show_window()),
            Menu.SEPARATOR,
            Item("Check Status", lambda icon, item: _check_status_notification()),
            Menu.SEPARATOR,
            Item("Quit",         _quit_app),
        )
    except Exception:
        return None


def _check_status_notification():
    """Tray menu → Check Status → fires a notification with current health."""
    data = _fetch_json("/cognitive/health-score")
    if data:
        score = data.get("score", "?")
        grade = data.get("grade", "?")
        _send_notification(
            "CVIS — System Status",
            f"Health: {score}/1000 ({grade})\nSeverity: {_last_sev}",
        )
    else:
        _send_notification("CVIS", "Backend not responding.")


def _start_tray():
    """Run the system tray icon (blocking — run in its own thread)."""
    global _tray
    try:
        import pystray

        img  = _make_tray_image("LOW")
        menu = _build_tray_menu()

        _tray = pystray.Icon(
            name="cvis",
            icon=img,
            title="CVIS — Cognitive AIOps",
            menu=menu,
        )
        _tray.run()
    except ImportError:
        log.warning("pystray not available — tray icon disabled")
    except Exception as e:
        log.warning("Tray error: %s", e)


# ─────────────────────────────────────────────────────────
#  Window event handlers
# ─────────────────────────────────────────────────────────

def _on_minimise():
    """When window is minimised, hide it and keep running in tray."""
    _hide_window()
    _send_notification(
        "CVIS is still running",
        "CVIS is monitoring your system in the background. Click the tray icon to reopen.",
    ) if _last_notif_at == 0.0 else None


def _on_closing():
    """
    When X is clicked — minimise to tray instead of quitting.
    Return False to prevent pywebview from destroying the window.
    """
    _hide_window()
    return False


# ─────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────

def main():
    global _window

    # 1. Start backend thread
    backend_thread = threading.Thread(target=_start_backend, daemon=True, name="cvis-backend")
    backend_thread.start()

    # 2. Wait for backend to be ready
    print("Starting CVIS…")
    ready = _wait_for_backend(timeout=30)
    if not ready:
        _send_notification("CVIS — Error", "Backend failed to start. Check cvis_app.log.")

    # 3. Start alert poller thread
    poller_thread = threading.Thread(target=_alert_poller, daemon=True, name="cvis-poller")
    poller_thread.start()

    # 4. Start tray in its own thread
    tray_thread = threading.Thread(target=_start_tray, daemon=True, name="cvis-tray")
    tray_thread.start()

    # 5. Create and show the native window
    try:
        import webview

        _window = webview.create_window(
            title=APP_TITLE,
            url=BACKEND_URL if ready else "about:blank",
            width=WINDOW_W,
            height=WINDOW_H,
            min_size=(MIN_W, MIN_H),
            resizable=True,
            background_color="#0a0a0f",
            text_select=False,
            zoomable=False,
        )

        # Hook minimise → go to tray
        # pywebview exposes events on the window object
        _window.events.minimized  += _on_minimise
        _window.events.closing    += _on_closing

        # Start the GUI event loop (blocking)
        webview.start(
            debug=False,
            private_mode=False,
            storage_path=os.path.join(os.path.expanduser("~"), ".cvis"),
        )

    except ImportError:
        log.error("pywebview not installed. Run: pip install pywebview")
        input("pywebview not found. Press Enter to exit.")
    except Exception as e:
        log.error("Window error: %s", e)
        input(f"Window failed: {e}\nPress Enter to exit.")


if __name__ == "__main__":
    main()
