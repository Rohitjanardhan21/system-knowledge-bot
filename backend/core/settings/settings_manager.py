"""
CVIS Settings Manager
Thread-safe settings store persisted to data/settings.json
Reads .env as defaults, overrides with saved JSON settings.
"""
import os, json, threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()

# ── Default settings (mirrors .env) ──────────────────────────────────────────
DEFAULTS: dict[str, Any] = {
    # Notifications
    "email_alerts_enabled":   True,
    "smtp_host":              os.environ.get("SMTP_HOST",  "smtp.gmail.com"),
    "smtp_port":              int(os.environ.get("SMTP_PORT", "587")),
    "smtp_user":              os.environ.get("SMTP_USER",  ""),
    "smtp_pass":              "",   # never written to defaults — read from env only
    "alert_email":            os.environ.get("ALERT_EMAIL", ""),
    "alert_min_severity":     os.environ.get("ALERT_MIN_SEVERITY", "HIGH"),
    "alert_cooldown_s":       int(os.environ.get("ALERT_EMAIL_COOLDOWN_S", "300")),
    "desktop_notifications":  False,
    "weekly_report_enabled":  False,

    # Alert thresholds
    "threshold_cpu":     80.0,
    "threshold_memory":  80.0,
    "threshold_disk":    85.0,
    "threshold_anomaly": 0.70,
    "threshold_health":  400.0,

    # Monitoring
    "poll_interval_s":        1,
    "autosave_interval_s":    300,
    "startup_grace_s":        30,
    "auto_remediation_mode":  os.environ.get("AUTO_REMEDIATE", "dry_run"),
    "blackbox_retention_min": 120,

    # Dashboard panels
    "refresh_rate_ms":        3000,
    "show_forecast":          True,
    "show_premortem":         True,
    "show_blackbox":          True,
    "show_processes":         True,
    "show_correlations":      True,
    "show_ml_signals":        True,
}

def _settings_path() -> Path:
    base = os.environ.get("DB_PATH", "data/cvis.db")
    data_dir = Path(base).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "settings.json"

def _load_from_disk() -> dict:
    p = _settings_path()
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_to_disk(data: dict):
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, indent=2)

# ── In-memory store ───────────────────────────────────────────────────────────
_store: dict[str, Any] = {}

def _init():
    global _store
    merged = dict(DEFAULTS)
    merged.update(_load_from_disk())
    # Always pull smtp_pass from env — never store in JSON
    merged["smtp_pass"] = os.environ.get("SMTP_PASS", os.environ.get("SMTP_PASSWORD", ""))
    _store = merged

_init()

# ── Public API ────────────────────────────────────────────────────────────────

def get_all() -> dict:
    with _lock:
        out = dict(_store)
    out["smtp_pass"] = "••••••••" if out.get("smtp_pass") else ""
    return out

def get(key: str, default=None):
    with _lock:
        return _store.get(key, default)

def save(updates: dict) -> dict:
    """Merge updates into store, persist, sync env."""
    with _lock:
        # Keep actual smtp_pass from env if client sends redacted value
        if updates.get("smtp_pass", "").startswith("•"):
            updates.pop("smtp_pass", None)
        _store.update(updates)
        to_disk = {k: v for k, v in _store.items() if k != "smtp_pass"}
        _save_to_disk(to_disk)
        _sync_env(_store)
    return get_all()

def reset() -> dict:
    """Reset to .env / compile-time defaults."""
    with _lock:
        _store.clear()
        _store.update(DEFAULTS)
        _store["smtp_pass"] = os.environ.get("SMTP_PASS", os.environ.get("SMTP_PASSWORD", ""))
        _save_to_disk({k: v for k, v in _store.items() if k != "smtp_pass"})
        _sync_env(_store)
    return get_all()

def apply_alert_thresholds(alert_engine):
    """Push threshold settings into the live alert engine rules."""
    mapping = {
        "cpu_high":     ("threshold_cpu",     "cpu_percent"),
        "memory_high":  ("threshold_memory",  "memory"),
        "disk_high":    ("threshold_disk",    "disk_percent"),
        "anomaly_high": ("threshold_anomaly", "anomaly_score"),
    }
    with _lock:
        for rule_id, (setting_key, _) in mapping.items():
            val = _store.get(setting_key)
            if val is not None:
                try:
                    alert_engine.update_rule(rule_id, threshold=float(val))
                except Exception:
                    pass

def _sync_env(store: dict):
    """Sync critical keys to os.environ so they take effect without restart."""
    env_map = {
        "smtp_host":          "SMTP_HOST",
        "smtp_port":          "SMTP_PORT",
        "smtp_user":          "SMTP_USER",
        "smtp_pass":          "SMTP_PASS",
        "alert_email":        "ALERT_EMAIL",
        "alert_min_severity": "ALERT_MIN_SEVERITY",
        "alert_cooldown_s":   "ALERT_EMAIL_COOLDOWN_S",
        "poll_interval_s":    "POLL_INTERVAL_S",
        "autosave_interval_s":"AUTOSAVE_INTERVAL_S",
        "auto_remediation_mode": "AUTO_REMEDIATE",
    }
    for key, env_key in env_map.items():
        val = store.get(key)
        if val is not None:
            os.environ[env_key] = str(val)
