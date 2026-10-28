"""
CVIS Desktop App
================
Native application window + system tray integration.
Behaves like ArmouryCrate — window when you want it, tray when you don't.

Double-click CVIS.exe:
  -> Loading screen appears immediately
  -> Backend starts silently in background
  -> Dashboard loads automatically when backend is ready
  -> Minimising goes to tray
  -> Tray icon turns red/orange on alerts
  -> Windows notifications fire on predictions

Build:
  python -m PyInstaller build_app.spec --clean --noconfirm
"""

import sys
import os
import secrets
import threading
import time
import json
import logging
import urllib.request
import urllib.error

if getattr(sys, "frozen", False):
    if sys.platform == "win32":
        _data_root = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local"
        )
        APP_DATA_DIR = os.path.join(_data_root, "CVIS")
    elif sys.platform == "darwin":
        APP_DATA_DIR = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", "CVIS"
        )
    else:
        APP_DATA_DIR = os.path.join(
            os.environ.get(
                "XDG_DATA_HOME",
                os.path.join(os.path.expanduser("~"), ".local", "share"),
            ),
            "cvis",
        )
else:
    APP_DATA_DIR = os.path.dirname(os.path.abspath(__file__))

def _make_standard_streams_safe():
    # Windowed builds may have no console streams, and legacy code pages
    # cannot encode characters such as "→" that appear in log messages.
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
        elif hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_make_standard_streams_safe()

for _directory in ("data", "logs", "model_versions"):
    os.makedirs(os.path.join(APP_DATA_DIR, _directory), exist_ok=True)

def _load_local_configuration():
    env_path = os.path.join(APP_DATA_DIR, ".env")
    configured = {}

    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                configured[key.strip()] = value.strip().strip("\"'")

    for key, value in configured.items():
        if value:
            os.environ.setdefault(key, value)

    defaults = {
        "ENV": "dev",
        "CVIS_ADMIN_USER": "admin",
        "CVIS_ADMIN_PASS": secrets.token_urlsafe(24),
        "CVIS_API_KEY": secrets.token_urlsafe(32),
        "JWT_SECRET": secrets.token_hex(32),
        "ALLOWED_ORIGIN": f"http://localhost:{PORT},http://127.0.0.1:{PORT}",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)

    persisted = dict(configured)
    persisted.update({key: os.environ[key] for key in defaults})
    with open(env_path, "w", encoding="utf-8") as env_file:
        env_file.writelines(f"{key}={value}\n" for key, value in persisted.items())
    if os.name != "nt":
        os.chmod(env_path, 0o600)


# Suppress console window on Windows
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0
        )
    except Exception:
        pass

# Logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(APP_DATA_DIR, "logs", "cvis_app.log"), encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("cvis.app")

# Constants
BACKEND_URL  = "http://localhost:9000"   # port 9000 — avoids Windows reserved ports
WINDOW_W     = 1440
WINDOW_H     = 900
MIN_W        = 1024
MIN_H        = 700
POLL_SECONDS = 10
APP_TITLE    = "CVIS — Cognitive AIOps"
PORT         = 9000
_load_local_configuration()
API_KEY = os.environ["CVIS_API_KEY"]
SETTINGS_PATH = os.path.join(APP_DATA_DIR, "settings.json")
os.environ["CVIS_DESKTOP_SETTINGS_PATH"] = SETTINGS_PATH
from backend.desktop_settings import (
    read_settings as _read_saved_settings,
    write_settings as _write_saved_settings,
)


def _read_desktop_settings() -> dict:
    try:
        return _read_saved_settings()
    except (OSError, json.JSONDecodeError) as exc:
        log.error("Could not read desktop preferences: %s", exc)
        return {"configured": False, "background_monitoring": False}


def _write_desktop_settings(background_monitoring: bool) -> dict:
    try:
        return _write_saved_settings(background_monitoring)
    except (OSError, RuntimeError) as exc:
        log.error("Could not save desktop preferences: %s", exc)
        raise

# Shared state
_window        = None
_tray          = None
_last_sev      = "LOW"
_backend_up    = False
_last_pred_id  = None
_last_notif_at = 0.0
_backend_server = None
_backend_thread = None
_backend_lock = threading.RLock()
_backend_stop_requested = threading.Event()
_shutdown_event = threading.Event()
_quit_lock = threading.Lock()
_quit_started = False
_poller_thread = None
_window_visible = False
_opening_dashboard = False
_navigation_lock = threading.Lock()


# Loading screen HTML
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
  <div class="log">Check the CVIS application-data logs and .env file for details and local login credentials.</div>
</body>
</html>"""

FIRST_RUN_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  *{box-sizing:border-box}
  body{margin:0;background:#0a0a0f;color:#e8e8f0;font:14px system-ui,sans-serif;
    display:grid;place-items:center;min-height:100vh;padding:28px}
  main{width:min(700px,100%)}
  h1{color:#7c6af7;margin:0 0 8px}
  p{color:#a9a9c0;line-height:1.55}
  .choices{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:24px}
  button{min-height:150px;text-align:left;padding:18px;background:#111522;color:#e8e8f0;
    border:1px solid #37364e;border-radius:8px;cursor:pointer;font:inherit}
  button:enabled:hover{border-color:#7c6af7;background:#171a2a}
  button:disabled{opacity:.55;cursor:wait}
  strong{display:block;color:#fff;font-size:16px;margin-bottom:10px}
  small{display:block;color:#a9a9c0;line-height:1.5}
  #status{min-height:22px;color:#c4bcff;margin-top:14px}
  @media(max-width:560px){.choices{grid-template-columns:1fr}}
</style>
</head>
<body>
  <main>
    <h1>Choose how CVIS should run</h1>
    <p>You can change this preference later in Settings. CVIS has not measured its idle CPU or memory use, so it makes no numerical resource claim.</p>
    <div class="choices">
      <button id="background" disabled onclick="choose(true)">
        <strong>Background monitoring</strong>
        <small>Keep CVIS monitoring while its dashboard is hidden. The tray icon remains available until you quit.</small>
      </button>
      <button id="ondemand" disabled onclick="choose(false)">
        <strong>On-demand</strong>
        <small>Use the dashboard when open. Hiding it stops the backend and collection; reopen it when you want to analyze logs or view the dashboard.</small>
      </button>
    </div>
    <div id="status" role="status"></div>
  </main>
  <script>
    window.addEventListener("pywebviewready", () => {
      document.querySelectorAll("button").forEach(button => button.disabled = false);
    });
    async function choose(enabled) {
      document.querySelectorAll("button").forEach(button => button.disabled = true);
      document.getElementById("status").textContent = "Starting CVIS…";
      try {
        await window.pywebview.api.choose_usage_mode(enabled);
      } catch {
        document.getElementById("status").textContent = "Could not save this choice. Please try again.";
        document.querySelectorAll("button").forEach(button => button.disabled = false);
      }
    }
  </script>
</body>
</html>"""


# Backend launcher
def _start_backend():
    global _backend_up, _backend_server, _backend_thread
    try:
        os.chdir(APP_DATA_DIR)

        if not os.environ.get("DB_PATH"):
            os.environ["DB_PATH"] = os.path.join(
                APP_DATA_DIR, "data", "cvis.db"
            )
        log.info("DB_PATH set to %s", os.environ["DB_PATH"])

        import uvicorn
        from backend.main import app as fastapi_app

        log.info("Starting CVIS backend on %s", BACKEND_URL)
        server = uvicorn.Server(uvicorn.Config(
            fastapi_app,
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
            access_log=False,
            timeout_graceful_shutdown=2,
            timeout_keep_alive=1,
        ))
        with _backend_lock:
            _backend_server = server
            if _backend_stop_requested.is_set():
                server.should_exit = True
        server.run()
    except Exception as e:
        log.error("Backend failed to start: %s", e)
    finally:
        with _backend_lock:
            _backend_up = False
            _backend_server = None
            _backend_thread = None


def _ensure_backend():
    global _backend_thread
    while True:
        if _shutdown_event.is_set():
            return
        with _backend_lock:
            thread = _backend_thread
            if thread is not None and thread.is_alive():
                if not _backend_stop_requested.is_set():
                    return
            else:
                _backend_stop_requested.clear()
                _backend_thread = threading.Thread(
                    target=_start_backend, daemon=True, name="cvis-backend"
                )
                _backend_thread.start()
                return
        thread.join(20.0)
        if thread.is_alive():
            log.error("Previous backend instance is still stopping")
            return


def _stop_backend(timeout: float = 8.0, wait: bool = True):
    global _backend_up
    _backend_stop_requested.set()
    with _backend_lock:
        _backend_up = False
        server = _backend_server
        thread = _backend_thread
        if server is not None:
            server.should_exit = True
    if not wait:
        return
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout)
        if thread.is_alive():
            log.error("Backend did not stop within %.1f seconds", timeout)


def _wait_for_backend(timeout: int = 60) -> bool:
    global _backend_up
    deadline = time.time() + timeout
    while time.time() < deadline and not _shutdown_event.is_set():
        try:
            req = urllib.request.Request(
                f"{BACKEND_URL}/health",
                headers={"X-API-Key": API_KEY},
            )
            with urllib.request.urlopen(req, timeout=2):
                _backend_up = True
                return True
        except Exception:
            _shutdown_event.wait(1.0)
    _backend_up = False
    if not _shutdown_event.is_set():
        log.error("Backend health check failed after %s seconds", timeout)
    return False


# Notifications
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


# Alert poller
def _fetch_json(path: str):
    if _shutdown_event.is_set():
        return None
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
    while not _shutdown_event.is_set():
        if not _backend_up:
            _shutdown_event.wait(2)
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
        _shutdown_event.wait(POLL_SECONDS)


# Tray icon
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


def _show_window(force_reload: bool = False):
    global _opening_dashboard
    with _navigation_lock:
        if _opening_dashboard:
            return
        _opening_dashboard = True
    threading.Thread(
        target=_open_dashboard_when_ready,
        kwargs={"force_reload": force_reload},
        daemon=True,
        name="cvis-open-dashboard",
    ).start()


def _open_dashboard_when_ready(force_reload: bool = False):
    global _opening_dashboard, _window_visible
    try:
        if _shutdown_event.is_set():
            return
        if _window:
            _window.show()
            _window.restore()
            _window_visible = True
            if _backend_up and not force_reload:
                return
            if not _backend_up:
                _window.load_html(LOADING_HTML)
        _ensure_backend()
        if not _shutdown_event.is_set() and _wait_for_backend(timeout=60):
            if _window:
                _window.load_url(BACKEND_URL)
        elif _window and not _shutdown_event.is_set():
            _window.load_html(ERROR_HTML)
    except Exception as exc:
        log.error("Could not open the dashboard: %s", exc)
    finally:
        with _navigation_lock:
            _opening_dashboard = False


def _hide_window():
    global _window, _window_visible
    if _shutdown_event.is_set():
        return
    _window_visible = False
    if _window:
        try:
            _window.hide()
        except Exception:
            pass
    if not _read_desktop_settings()["background_monitoring"]:
        threading.Thread(
            target=_stop_backend,
            daemon=True,
            name="cvis-stop-on-demand-backend",
        ).start()


def _quit_app(icon=None, item=None):
    global _quit_started, _window_visible
    with _quit_lock:
        if _quit_started:
            return
        _quit_started = True
    _shutdown_event.set()
    _window_visible = False
    _stop_backend(wait=False)
    try:
        if _tray:
            _tray.stop()
    except Exception:
        log.exception("Could not remove the CVIS tray icon during shutdown")
    try:
        if _window:
            _window.destroy()
    except Exception:
        log.exception("Could not close the CVIS window during shutdown")


def _set_background_monitoring(enabled: bool, icon=None):
    try:
        current = _read_desktop_settings()["background_monitoring"]
        if enabled == current:
            return
        _write_desktop_settings(enabled)
        if icon:
            icon.update_menu()
        if enabled:
            _ensure_backend()
            _send_notification(
                "CVIS background monitoring enabled",
                "Monitoring will continue when the dashboard is hidden.",
            )
        elif not _window_visible:
            threading.Thread(
                target=_stop_backend,
                daemon=True,
                name="cvis-stop-background-monitoring",
            ).start()
            _send_notification(
                "CVIS switched to on-demand",
                "Monitoring stops while the dashboard is hidden.",
            )
        else:
            _send_notification(
                "CVIS switched to on-demand",
                "Monitoring will stop when you hide the dashboard.",
            )
    except OSError as exc:
        log.error("Could not change background monitoring preference: %s", exc)


def _enable_background_monitoring(icon, item):
    _set_background_monitoring(True, icon)


def _use_on_demand_mode(icon, item):
    _set_background_monitoring(False, icon)


class DesktopApi:
    def get_api_key(self):
        """Return the local backend key to the bundled desktop webview only."""
        return API_KEY

    def choose_usage_mode(self, background_monitoring: bool):
        _write_desktop_settings(bool(background_monitoring))
        _show_window(force_reload=True)
        if _tray:
            _tray.update_menu()
        return {"saved": True}

    def quit_cvis(self):
        threading.Thread(
            target=_quit_app,
            name="cvis-quit",
        ).start()
        return {"status": "shutting_down"}


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
            Item(
                "Background monitoring",
                _enable_background_monitoring,
                checked=lambda item: _read_desktop_settings()["background_monitoring"],
                radio=True,
            ),
            Item(
                "On-demand (pause when hidden)",
                _use_on_demand_mode,
                checked=lambda item: not _read_desktop_settings()["background_monitoring"],
                radio=True,
            ),
            Item("Open Dashboard", lambda icon, item: _show_window(), default=True),
            Menu.SEPARATOR,
            Item("Quit CVIS", _quit_app),
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


# Window event handlers
_minimise_notif_sent = False

def _on_minimise():
    global _minimise_notif_sent
    _hide_window()
    if not _minimise_notif_sent:
        _minimise_notif_sent = True
        if _read_desktop_settings()["background_monitoring"]:
            _send_notification(
                "CVIS is still running",
                "Background monitoring continues. Click the tray icon to reopen.",
            )
        else:
            _send_notification(
                "CVIS is paused",
                "Monitoring stopped while hidden. Click the tray icon to reopen.",
            )


def _on_closing():
    """X button goes to tray instead of quitting."""
    if _shutdown_event.is_set():
        return True
    _hide_window()
    return False


# Main
def main():
    global _window, _window_visible, _poller_thread

    _poller_thread = threading.Thread(
        target=_alert_poller, daemon=True, name="cvis-poller"
    )
    _poller_thread.start()
    threading.Thread(target=_start_tray,    daemon=True, name="cvis-tray").start()

    try:
        import webview

        settings = _read_desktop_settings()
        _window = webview.create_window(
            title=APP_TITLE,
            html=LOADING_HTML if settings["configured"] else FIRST_RUN_HTML,
            width=WINDOW_W,
            height=WINDOW_H,
            min_size=(MIN_W, MIN_H),
            resizable=True,
            background_color="#0a0a0f",
            text_select=False,
            zoomable=False,
            js_api=DesktopApi(),
        )
        _window_visible = True

        _window.events.minimized += _on_minimise
        _window.events.closing   += _on_closing

        if settings["configured"]:
            _ensure_backend()

            def _navigate_when_ready():
                try:
                    if _wait_for_backend(timeout=60):
                        _window.load_url(BACKEND_URL)
                    else:
                        _window.load_html(ERROR_HTML)
                except Exception as e:
                    log.error("Navigation error: %s", e)

            threading.Thread(
                target=_navigate_when_ready, daemon=True, name="cvis-nav"
            ).start()

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