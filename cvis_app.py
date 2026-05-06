"""
CVIS Desktop App
================
Native application window + system tray integration.
Behaves like ArmouryCrate — window when you want it, tray when you don't.

Double-click CVIS.exe:
  → Loading screen appears immediately
  → Backend starts silently in background
  → Dashboard loads automatically when backend is ready
  → Minimising goes to tray
  → Tray icon turns red/orange on alerts
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
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0
        )
    except Exception:
        pass

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("cvis_app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("cvis.app")

# ── Constants ─────────────────────────────────────────────
BACKEND_URL  = "http://127.0.0.1:8000"
API_KEY      = "test123"
WINDOW_W     = 1440
WINDOW_H     = 900
MIN_W        = 1024
MIN_H        = 700
POLL_SECONDS = 10
APP_TITLE    = "CVIS — Cognitive AIOps"

# ── Shared state ──────────────────────────────────────────
_window        = None
_tray          = None
_last_sev      = "LOW"
_backend_up    = False
_shutdown      = False
_last_pred_id  = None
_last_notif_at = 0.0


# ─────────────────────────────────────────────────────────
#  Loading screen HTML
# ─────────────────────────────────────────────────────────

LOADING_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;600&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    background: #0a0a0f;
    color: #e8e8f0;
    font-family: 'IBM Plex Mono', monospace;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    gap: 18px;
    user-select: none;
  }
  .logo { font-size: 32px; font-weight: 600; color: #7c6af7; letter-spacing: .12em; }
  .logo span { color: #555570; font-weight: 300; }
  .tagline { font-size: 11px; color: #555570; letter-spacing: .12em; text-transform: uppercase; }
  .bar-track {
    width: 300px; height: 2px;
    background: rgba(255,255,255,.06);
    border-radius: 2px; overflow: hidden; margin-top: 8px;
  }
  .bar-fill {
    height: 100%; width: 0%; background: #7c6af7;
    border-radius: 2px; animation: load 12s ease forwards;
  }
  @keyframes load {
    0%{width:0%} 20%{width:20%} 40%{width:45%}
    65%{width:68%} 85%{width:85%} 100%{width:96%}
  }
  .status { font-size: 11px; color: #333350; margin-top: 4px; animation: fade 3s ease infinite alternate; }
  @keyframes fade { from{opacity:.4} to{opacity:1} }
  .dots { display: flex; gap: 8px; margin-top: 6px; }
  .dot {
    width: 5px; height: 5px; border-radius: 50%;
    background: #7c6af7; animation: bounce 1.2s infinite;
  }
  .dot:nth-child(2){animation-delay:.2s}
  .dot:nth-child(3){animation-delay:.4s}
  @keyframes bounce {
    0%,60%,100%{transform:translateY(0);opacity:.3}
    30%{transform:translateY(-6px);opacity:1}
  }
</style>
</head>
<body>
  <div class="logo">CVIS <span>/ Cognitive AIOps</span></div>
  <div class="tagline">Predicts failures before they happen</div>
  <div class="bar-track"><div class="bar-fill"></div></div>
  <div class="status">Starting ML engine and cognitive layer...</div>
  <div class="dots">
    <div class="dot"></div><div class="dot"></div><div class="dot"></div>
  </div>
</body>
</html>"""

ERROR_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{
    background:#0a0a0f;color:#f87171;font-family:monospace;
    display:flex;flex-direction:column;align-items:center;
    justify-content:center;height:100vh;gap:12px;
    text-align:center;padding:40px;
  }
  .title{font-size:20px;font-weight:600}
  .sub{font-size:12px;color:#555570;line-height:1.7}
  .log{font-size:11px;color:#333350;margin-top:8px}
</style>
</head>
<body>
  <div class="title">Backend failed to start</div>
  <div class="sub">
    The CVIS backend did not respond within 60 seconds.<br>
    This usually means a missing dependency or port conflict.
  </div>
  <div class="log">Check cvis_app.log for details.</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────
#  Backend launcher
# ─────────────────────────────────────────────────────────

def _start_backend():
    global _backend_up
    try:
        os.makedirs("data",           exist_ok=True)
        os.makedirs("logs",           exist_ok=True)
        os.makedirs("model_versions", exist_ok=True)

        if not os.path.exists(".env") and os.path.exists(".env.example"):
            import shutil
            shutil.copy(".env.example", ".env")
            log.info("Created .env from .env.example")

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


def _wait_for_backend(timeout: int = 60) -> bool:
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
#  Notifications
# ─────────────────────────────────────────────────────────

def _send_notification(title: str, message: str):
    if sys.platform != "win32":
        return
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=8, threaded=True)
    except Exception:
        try:
            import subprocess
            t = title.replace("'", "")
            m = message.replace("'", "").replace("\n", " ")
            ps = (
                f"Add-Type -AssemblyName System.Windows.Forms;"
                f"$n=New-Object System.Windows.Forms.NotifyIcon;"
                f"$n.Icon=[System.Drawing.SystemIcons]::Information;"
                f"$n.Visible=$true;"
                f"$n.ShowBalloonTip(8000,'{t}','{m}',"
                f"[System.Windows.Forms.ToolTipIcon]::Warning);"
                f"Start-Sleep -s 9;$n.Dispose()"
            )
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
                creationflags=0x08000000,
            )
        except Exception as e:
            log.warning("Notification failed: %s", e)


# ─────────────────────────────────────────────────────────
#  Alert poller
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


def _alert_poller():
    global _last_sev, _last_pred_id, _last_notif_at
    while not _shutdown:
        if not _backend_up:
            time.sleep(2)
            continue
        try:
            preds = _fetch_json("/cognitive/predictions")
            if preds:
                pred = preds[0]
                pid  = pred.get("id")
                sev  = pred.get("severity", "LOW")
                eta  = int(pred.get("eta_minutes", 0))
                msg  = pred.get("message", "")
                conf = int(pred.get("confidence", 0))
                now  = time.time()
                if pid != _last_pred_id and now - _last_notif_at > 60:
                    _last_pred_id  = pid
                    _last_notif_at = now
                    _send_notification(
                        f"CVIS — {sev} Alert",
                        f"{msg}\nExpected in ~{eta} min ({conf}% confidence)",
                    )
                _last_sev = sev
            else:
                health = _fetch_json("/health")
                if health:
                    _last_sev = health.get("severity", "LOW")
            _update_tray_icon()
        except Exception as e:
            log.debug("Poller error: %s", e)
        time.sleep(POLL_SECONDS)


# ─────────────────────────────────────────────────────────
#  Tray icon
# ─────────────────────────────────────────────────────────

def _make_tray_image(severity: str = "LOW"):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    size = 64
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    colors = {
        "LOW":      "#34d399",
        "MEDIUM":   "#fbbf24",
        "HIGH":     "#fb923c",
        "CRITICAL": "#f87171",
    }
    c = colors.get(severity, "#34d399")
    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    draw.ellipse([2,  2,  size-2,  size-2],  outline=c, width=4)
    draw.ellipse([10, 10, size-10, size-10], fill=(r, g, b, 110))
    if severity == "CRITICAL":
        draw.rectangle([30, 14, 34, 36], fill=(r, g, b, 255))
        draw.ellipse(  [30, 42, 34, 46], fill=(r, g, b, 255))
    return img


def _update_tray_icon():
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
    try:
        if _tray:   _tray.stop()
    except Exception:
        pass
    try:
        if _window: _window.destroy()
    except Exception:
        pass
    sys.exit(0)


def _check_status_notification():
    data = _fetch_json("/cognitive/health-score")
    if data:
        score = data.get("score", "?")
        grade = data.get("grade", "?")
        _send_notification(
            "CVIS — System Status",
            f"Health: {score}/1000 ({grade})  Severity: {_last_sev}",
        )
    else:
        _send_notification("CVIS", "Backend not responding.")


def _build_tray_menu():
    try:
        from pystray import MenuItem as Item, Menu
        return Menu(
            Item("Open CVIS",    lambda icon, item: _show_window(), default=True),
            Item("Dashboard",    lambda icon, item: _show_window()),
            Menu.SEPARATOR,
            Item("Check Status", lambda icon, item: _check_status_notification()),
            Menu.SEPARATOR,
            Item("Quit CVIS",    _quit_app),
        )
    except Exception:
        return None


def _start_tray():
    global _tray
    try:
        import pystray
        _tray = pystray.Icon(
            name="cvis",
            icon=_make_tray_image("LOW"),
            title="CVIS — Cognitive AIOps",
            menu=_build_tray_menu(),
        )
        _tray.run()
    except ImportError:
        log.warning("pystray not available — tray icon disabled")
    except Exception as e:
        log.warning("Tray error: %s", e)


# ─────────────────────────────────────────────────────────
#  Window event handlers
# ─────────────────────────────────────────────────────────

_minimise_notif_sent = False

def _on_minimise():
    global _minimise_notif_sent
    _hide_window()
    if not _minimise_notif_sent:
        _minimise_notif_sent = True
        _send_notification(
            "CVIS is still running",
            "Monitoring continues in the background. Click the tray icon to reopen.",
        )


def _on_closing():
    """X button goes to tray instead of quitting."""
    _hide_window()
    return False


# ─────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────

def main():
    global _window

    # Start backend, poller, tray in background threads
    threading.Thread(target=_start_backend, daemon=True, name="cvis-backend").start()
    threading.Thread(target=_alert_poller,  daemon=True, name="cvis-poller").start()
    threading.Thread(target=_start_tray,    daemon=True, name="cvis-tray").start()

    try:
        import webview

        # Show loading screen immediately — no waiting
        _window = webview.create_window(
            title=APP_TITLE,
            html=LOADING_HTML,
            width=WINDOW_W,
            height=WINDOW_H,
            min_size=(MIN_W, MIN_H),
            resizable=True,
            background_color="#0a0a0f",
            text_select=False,
            zoomable=False,
        )

        _window.events.minimized += _on_minimise
        _window.events.closing   += _on_closing

        # Wait for backend in a thread, then navigate
        def _navigate_when_ready():
            ready = _wait_for_backend(timeout=60)
            time.sleep(0.3)
            if ready:
                _window.load_url(BACKEND_URL)
            else:
                _window.load_html(ERROR_HTML)

        threading.Thread(
            target=_navigate_when_ready, daemon=True, name="cvis-nav"
        ).start()

        # Blocks until window is closed
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
        input(f"Window error: {e}\nPress Enter to exit.")


if __name__ == "__main__":
    main()
