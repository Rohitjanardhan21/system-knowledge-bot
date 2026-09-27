import os
import sys
from pathlib import Path

# Add project root to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ------------------------------------------------------------------
# Test environment MUST be established before ANY backend import.
# Several test modules import backend.main during pytest collection.
# ------------------------------------------------------------------
os.environ.setdefault("CVIS_API_KEY", "test-bootstrap-key-abc123")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-prod-2026")
os.environ.setdefault("CVIS_ADMIN_PASS", "test-admin-pass")
os.environ.setdefault("CVIS_ADMIN_USER", "admin")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
