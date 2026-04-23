"""
CVIS Standalone Launcher
Works on Windows, macOS, Linux
No Docker required

Usage:
    python app.py
    python app.py --port 8000 --no-browser
"""
import os
import sys
import time
import signal
import platform
import argparse
import threading
import subprocess
import webbrowser

OS = platform.system()

# ── Add project root to path ──────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

def check_dependencies():
    """Check all required packages are installed."""
    missing = []
    required = ["fastapi", "uvicorn", "psutil", "numpy", "sklearn", "torch", "pydantic"]
    for pkg in required:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    return missing

def start_redis():
    """Start Redis if available, otherwise skip (backend handles Redis absence)."""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379)
        r.ping()
        print("[CVIS] Redis already running")
        return None
    except Exception:
        pass

    # Try to start Redis
    redis_cmd = None
    if OS == "Windows":
        # Check common Windows Redis locations
        for path in [
            r"C:\Program Files\Redis\redis-server.exe",
            r"C:\Redis\redis-server.exe",
            "redis-server.exe",
        ]:
            if os.path.exists(path):
                redis_cmd = path
                break
    else:
        import shutil
        if shutil.which("redis-server"):
            redis_cmd = "redis-server"

    if redis_cmd:
        proc = subprocess.Popen(
            [redis_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        print("[CVIS] Redis started")
        return proc
    else:
        print("[CVIS] Redis not found — running without cache (degraded mode)")
        return None

def patch_env():
    """Set default environment variables if not already set."""
    defaults = {
        "CVIS_API_KEY":    "cvis-local",
        "JWT_SECRET":      "localdevkey123456789012345678901234",
        "CVIS_ADMIN_USER": "admin",
        "CVIS_ADMIN_PASS": "admin",
        "ENV":             "dev",
        "LOG_LEVEL":       "warning",
        "ALLOWED_ORIGIN":  "*",
        "REDIS_URL":       "redis://localhost:6379/0",
        "POLL_INTERVAL_S": "1",
        "DB_PATH":         os.path.join(ROOT, "data", "cvis.db"),
    }
    for k, v in defaults.items():
        if not os.environ.get(k):
            os.environ[k] = v

    # Create data directory
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "model_versions"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)

def open_browser(port, delay=3):
    """Open browser after backend starts."""
    def _open():
        time.sleep(delay)
        url = f"http://localhost:{port}"
        print(f"[CVIS] Opening dashboard at {url}")
        webbrowser.open(url)
    t = threading.Thread(target=_open, daemon=True)
    t.start()

def start_backend(port):
    """Start the FastAPI backend using uvicorn."""
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
        reload=False,
    )

def main():
    parser = argparse.ArgumentParser(description="CVIS AIOps — Standalone Launcher")
    parser.add_argument("--port",       default=8000, type=int, help="Port to run on (default: 8000)")
    parser.add_argument("--no-browser", action="store_true",    help="Don't open browser automatically")
    parser.add_argument("--check",      action="store_true",    help="Check dependencies only")
    args = parser.parse_args()

    print("=" * 55)
    print("  CVIS AIOps Engine — Standalone")
    print(f"  OS: {OS} {platform.release()}")
    print(f"  Python: {platform.python_version()}")
    print("=" * 55)

    # Check dependencies
    missing = check_dependencies()
    if missing:
        print(f"\n❌ Missing packages: {', '.join(missing)}")
        print(f"   Run: pip install {' '.join(missing)}")
        if args.check:
            sys.exit(1)
        print("\nInstalling missing packages...")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        print("✅ Dependencies installed\n")

    if args.check:
        print("✅ All dependencies satisfied")
        sys.exit(0)

    # Setup environment
    patch_env()

    # Start Redis (optional)
    redis_proc = start_redis()

    # Open browser
    if not args.no_browser:
        open_browser(args.port)

    # Handle shutdown
    def shutdown(sig, frame):
        print("\n[CVIS] Shutting down...")
        if redis_proc:
            redis_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"\n[CVIS] Starting backend on port {args.port}...")
    print(f"[CVIS] Dashboard: http://localhost:{args.port}")
    print(f"[CVIS] API key:   {os.environ['CVIS_API_KEY']}")
    print(f"[CVIS] Press Ctrl+C to stop\n")

    # Start backend (blocking)
    start_backend(args.port)

if __name__ == "__main__":
    main()
# This line intentionally left blank
