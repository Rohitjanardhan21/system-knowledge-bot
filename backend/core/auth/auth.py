"""
CVIS v9 — auth.py
Dual-mode authentication:
  1. API Keys  — static tokens in Redis/env, fast lookup, for machine-to-machine
  2. JWT Bearer — short-lived (15min) + refresh (7d) for browser sessions

Scopes:
  read    → GET /os /ml/status
  write   → POST /ml/scores, trigger simulations
  admin   → /models (versioning), /alerts (config), /auth (user mgmt)

All protected routes use: Depends(require_scope("read"))
Public routes:           /health, /nginx-health, /docs, /openapi.json
"""

import os, time, uuid, hashlib, secrets, logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader

log = logging.getLogger("cvis.auth")

# ── Optional deps ─────────────────────────────────────────
try:
    import jwt as _jwt   # PyJWT
    JWT_OK = True
except ImportError:
    JWT_OK = False
    log.warning("PyJWT not installed — JWT auth disabled, API-key only")

try:
    import bcrypt as _bcrypt  # noqa: F401
    BCRYPT_OK = True
except ImportError:
    BCRYPT_OK = False

try:
    import redis.asyncio as aioredis
    REDIS_OK = True
except ImportError:
    REDIS_OK = False

# ── Config ────────────────────────────────────────────────
def _read_secret(env_key: str) -> str:
    """
    Read a secret from:
      1. /run/secrets/<lower_key>  (Docker Swarm secrets — most secure)
      2. <env_key>_FILE env var    (path to any secret file)
      3. <env_key> env var         (plain env var — OK for dev, avoid in prod)
    """
    # 1. Docker Swarm secret file
    swarm_path = f"/run/secrets/{env_key.lower()}"
    if os.path.exists(swarm_path):
        return open(swarm_path).read().strip()
    # 2. Explicit file path in env
    file_path = os.environ.get(f"{env_key}_FILE")
    if file_path and os.path.exists(file_path):
        return open(file_path).read().strip()
    # 3. Plain env var (dev / docker-compose with env_file)
    return os.environ.get(env_key, "")

JWT_SECRET      = _read_secret("JWT_SECRET") or secrets.token_hex(32)
JWT_ALGORITHM   = "HS256"
ACCESS_TTL_S    = int(os.environ.get("JWT_ACCESS_TTL_S",  "900"))    # 15 min
REFRESH_TTL_S   = int(os.environ.get("JWT_REFRESH_TTL_S", "604800")) # 7 days

# Bootstrap admin API key
BOOTSTRAP_API_KEY = _read_secret("CVIS_API_KEY")
_api_key_store: dict[str, dict] = {}   # sha256(key) → {name, scope, created_at}

if not BOOTSTRAP_API_KEY:
    BOOTSTRAP_API_KEY = secrets.token_urlsafe(32)
    log.warning(
        "\n\n  *** NO CVIS_API_KEY SET — BOOTSTRAP KEY (save this, shown once) ***\n"
        "  %s\n"
        "  Production: set via Docker secret, _FILE env var, or .env\n",
        BOOTSTRAP_API_KEY,
    )

_hash = hashlib.sha256(BOOTSTRAP_API_KEY.encode()).hexdigest()
_api_key_store[_hash] = {"name": "bootstrap", "scope": "admin", "created_at": time.time()}

# ── Redis connection (for token revocation + key store) ───
_redis_client = None

async def get_redis():
    global _redis_client
    if _redis_client is None and REDIS_OK:
        try:
            _redis_client = aioredis.from_url(
                os.environ.get("REDIS_URL", "redis://redis:6379/0"),
                decode_responses=True, socket_connect_timeout=3,
            )
            await _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client

# ── Schemes ───────────────────────────────────────────────
bearer_scheme  = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# ── Token structures ──────────────────────────────────────
class TokenPair:
    def __init__(self, access: str, refresh: str, expires_in: int):
        self.access_token  = access
        self.refresh_token = refresh
        self.token_type    = "bearer"
        self.expires_in    = expires_in


def _issue_access_token(subject: str, scope: str) -> str:
    if not JWT_OK:
        raise HTTPException(501, "JWT not available — use API key")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "scope": scope,
        "iat": now,
        "exp": now + timedelta(seconds=ACCESS_TTL_S),
        "jti": uuid.uuid4().hex,
        "type": "access",
    }
    return _jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _issue_refresh_token(subject: str, scope: str) -> str:
    if not JWT_OK:
        raise HTTPException(501, "JWT not available")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "scope": scope,
        "iat": now,
        "exp": now + timedelta(seconds=REFRESH_TTL_S),
        "jti": uuid.uuid4().hex,
        "type": "refresh",
    }
    return _jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def issue_token_pair(subject: str, scope: str = "read") -> TokenPair:
    return TokenPair(
        access  = _issue_access_token(subject, scope),
        refresh = _issue_refresh_token(subject, scope),
        expires_in = ACCESS_TTL_S,
    )


async def _verify_jwt(token: str) -> dict:
    if not JWT_OK:
        raise HTTPException(501, "JWT not available")
    try:
        payload = _jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except _jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")

    # Check revocation in Redis (jti blocklist)
    redis = await get_redis()
    if redis:
        try:
            revoked = await redis.get(f"revoked_jti:{payload['jti']}")
            if revoked:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
        except Exception:
            pass   # Redis unavailable → skip revocation check

    return payload


async def _verify_api_key(key: str) -> dict:
    h = hashlib.sha256(key.encode()).hexdigest()
    # Check in-memory store first
    entry = _api_key_store.get(h)
    if entry:
        return entry
    # Then Redis
    redis = await get_redis()
    if redis:
        try:
            raw = await redis.hgetall(f"api_key:{h}")
            if raw:
                return raw
        except Exception:
            pass
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


# ── Main dependency: require_scope ────────────────────────
SCOPE_ORDER = ["read", "write", "admin"]

def _scope_gte(have: str, need: str) -> bool:
    try:
        return SCOPE_ORDER.index(have) >= SCOPE_ORDER.index(need)
    except ValueError:
        return False


def require_scope(needed: str = "read"):
    """
    FastAPI dependency factory.
    Usage:  Depends(require_scope("admin"))
    """
    async def _check(
        bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
        api_key: Optional[str] = Security(api_key_header),
    ) -> dict:
        principal: Optional[dict] = None

        if bearer and bearer.credentials:
            principal = await _verify_jwt(bearer.credentials)
            principal["_source"] = "jwt"
        elif api_key:
            principal = await _verify_api_key(api_key)
            principal["_source"] = "api_key"
        else:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Provide Bearer token or X-API-Key header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        scope = principal.get("scope", "read")
        if not _scope_gte(scope, needed):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Scope '{scope}' insufficient — need '{needed}'",
            )
        return principal

    return _check


# ── API key management ────────────────────────────────────
async def create_api_key(name: str, scope: str = "read") -> str:
    key = secrets.token_urlsafe(32)
    h   = hashlib.sha256(key.encode()).hexdigest()
    entry = {"name": name, "scope": scope, "created_at": str(time.time())}
    _api_key_store[h] = entry
    redis = await get_redis()
    if redis:
        try:
            await redis.hset(f"api_key:{h}", mapping=entry)
        except Exception:
            pass
    return key   # shown once — caller must store it


async def revoke_api_key(key_hash: str) -> bool:
    if key_hash in _api_key_store:
        del _api_key_store[key_hash]
    redis = await get_redis()
    if redis:
        try:
            await redis.delete(f"api_key:{key_hash}")
        except Exception:
            pass
    return True


async def revoke_jwt(jti: str, ttl: int = REFRESH_TTL_S):
    """Add JTI to Redis blocklist (expires after refresh TTL)."""
    redis = await get_redis()
    if redis:
        try:
            await redis.setex(f"revoked_jti:{jti}", ttl, "1")
        except Exception:
            pass


async def refresh_access_token(refresh_token: str) -> TokenPair:
    if not JWT_OK:
        raise HTTPException(501, "JWT not available")
    try:
        payload = _jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except _jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")
    # Rotate: revoke old refresh token
    await revoke_jwt(payload["jti"], REFRESH_TTL_S)
    return issue_token_pair(payload["sub"], payload.get("scope", "read"))


# ─────────────────────────────────────────────────────────
# SIMPLE API-KEY GUARD  (the pattern the docs describe)
# ─────────────────────────────────────────────────────────
# Three ready-to-use FastAPI dependencies that map to the
# READ / WRITE / ADMIN protection levels.
#
# Usage in routes:
#   from backend.core.auth.auth import read_guard, write_guard, admin_guard
#
#   @app.get("/os/status")                          # public
#   @app.post("/ml/scores", dependencies=[Depends(read_guard)])
#   @app.post("/models/save", dependencies=[Depends(admin_guard)])
#
# These are thin wrappers around require_scope() — the same
# JWT + API-key logic applies underneath.

read_guard  = require_scope("read")
write_guard = require_scope("write")
admin_guard = require_scope("admin")


# Minimal standalone guard — zero JWT, just X-API-Key header.
# Drop this in for the simplest possible protection pattern:
#
#   @app.post("/models/save", dependencies=[Depends(require_api_key)])
#
from fastapi import Header as _Header

def require_api_key(x_api_key: str = _Header(default=None)):
    """
    Simplest possible guard: checks X-API-Key == CVIS_API_KEY env var.
    Suitable for single-tenant / internal deployments.
    For multi-tenant or user-level access, use require_scope() instead.
    """
    expected = BOOTSTRAP_API_KEY
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return {"name": "api-key-user", "scope": "admin"}
