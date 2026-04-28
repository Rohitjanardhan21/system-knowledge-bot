"""
CVIS v9 — redis_store.py
Centralised Redis layer for:
  1. Alert deduplication (rule_id cooldowns survive restarts)
  2. API rate-limit hit counters (shared across Gunicorn workers)
  3. Recent metric snapshot cache (avoids re-querying psutil in every worker)
  4. Session / token store (refresh token blocklist, API key registry)
  5. Pub/Sub broadcast (multi-worker event log sync)
"""

import json, time, os, logging
from typing import Any, Optional

log = logging.getLogger("cvis.redis")

try:
    import redis.asyncio as aioredis
    REDIS_OK = True
except ImportError:
    REDIS_OK = False
    log.warning("redis package not installed — all Redis ops are no-ops")

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# ── Singleton client ──────────────────────────────────────
_client: Optional[Any] = None
_pubsub_client: Optional[Any] = None


async def get_client():
    global _client
    if not REDIS_OK:
        return None
    try:
        if _client is None:
            _client = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=False,
                max_connections=20,
            )
        await _client.ping()
        return _client
    except Exception as e:
        log.warning("Redis unavailable (%s) — falling back to in-memory", e)
        _client = None
        return None


async def is_healthy() -> bool:
    c = await get_client()
    if not c:
        return False
    try:
        await c.ping()
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# 1. ALERT DEDUPLICATION
#    key: cvis:alert_cooldown:{rule_id}
#    ttl: cooldown_seconds
# ─────────────────────────────────────────────────────────

async def alert_check_and_set(rule_id: str, cooldown_s: int) -> bool:
    """
    Returns True if this alert should fire (not in cooldown).
    Atomically sets the key so concurrent workers agree.
    Falls back to always-fire if Redis is unavailable.
    """
    c = await get_client()
    if not c:
        return True  # no Redis → fire (in-memory cooldown still applies)

    key = f"cvis:alert_cooldown:{rule_id}"
    try:
        # SET NX EX = set only if key doesn't exist, with TTL
        result = await c.set(key, "1", nx=True, ex=cooldown_s)
        return result is not None   # True = key was newly set = should fire
    except Exception as e:
        log.debug("alert_check_and_set error: %s", e)
        return True


async def alert_clear_cooldown(rule_id: str):
    c = await get_client()
    if not c:
        return
    try:
        await c.delete(f"cvis:alert_cooldown:{rule_id}")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────
# 2. RATE LIMIT COUNTERS (cross-worker)
#    key: cvis:rl:{identifier}:{window_start}
# ─────────────────────────────────────────────────────────

async def rate_limit_check(identifier: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
    """
    Sliding window rate limiter.
    Returns (allowed: bool, current_count: int).
    Falls back to (True, 0) if Redis unavailable.
    """
    c = await get_client()
    if not c:
        return True, 0

    now    = int(time.time())
    window = now - (now % window_s)
    key    = f"cvis:rl:{identifier}:{window}"

    try:
        pipe = c.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s * 2)
        results = await pipe.execute()
        count = results[0]
        return count <= limit, count
    except Exception as e:
        log.debug("rate_limit_check error: %s", e)
        return True, 0


# ─────────────────────────────────────────────────────────
# 3. METRIC SNAPSHOT CACHE
#    key: cvis:metrics:latest
#    ttl: 3s (fresher than poll interval)
# ─────────────────────────────────────────────────────────

async def cache_metrics(metrics: dict, ttl: int = 3):
    c = await get_client()
    if not c:
        return
    try:
        await c.setex("cvis:metrics:latest", ttl, json.dumps(metrics))
    except Exception:
        pass


async def get_cached_metrics() -> Optional[dict]:
    c = await get_client()
    if not c:
        return None
    try:
        raw = await c.get("cvis:metrics:latest")
        return json.loads(raw) if raw else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────
# 4. SESSION STORE — refresh token blocklist + API keys
# ─────────────────────────────────────────────────────────

async def blocklist_token(jti: str, ttl: int = 604800):
    """Add JWT JTI to blocklist (survives worker restarts)."""
    c = await get_client()
    if not c:
        return
    try:
        await c.setex(f"cvis:revoked_jti:{jti}", ttl, "1")
    except Exception:
        pass


async def is_token_revoked(jti: str) -> bool:
    c = await get_client()
    if not c:
        return False  # can't check → assume valid
    try:
        return bool(await c.exists(f"cvis:revoked_jti:{jti}"))
    except Exception:
        return False


async def store_api_key(key_hash: str, entry: dict, ttl: int = 0):
    """Persist API key entry. ttl=0 means no expiry."""
    c = await get_client()
    if not c:
        return
    try:
        r_key = f"cvis:api_key:{key_hash}"
        await c.hset(r_key, mapping={k: str(v) for k, v in entry.items()})
        if ttl > 0:
            await c.expire(r_key, ttl)
    except Exception:
        pass


async def get_api_key(key_hash: str) -> Optional[dict]:
    c = await get_client()
    if not c:
        return None
    try:
        data = await c.hgetall(f"cvis:api_key:{key_hash}")
        return data or None
    except Exception:
        return None


async def delete_api_key(key_hash: str):
    c = await get_client()
    if not c:
        return
    try:
        await c.delete(f"cvis:api_key:{key_hash}")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────
# 5. PUB/SUB — broadcast events to all Gunicorn workers
# ─────────────────────────────────────────────────────────
EVENTS_CHANNEL = "cvis:events"


async def publish_event(sev: str, msg: str):
    c = await get_client()
    if not c:
        return
    try:
        await c.publish(EVENTS_CHANNEL, json.dumps({"sev": sev, "msg": msg, "ts": time.time()}))
    except Exception:
        pass


async def subscribe_events(callback):
    """
    Subscribe to the events channel.
    Calls callback(sev, msg) for each message.
    Run in a background asyncio task.
    """
    if not REDIS_OK:
        return
    try:
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        ps = r.pubsub()
        await ps.subscribe(EVENTS_CHANNEL)
        async for message in ps.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await callback(data["sev"], data["msg"])
                except Exception:
                    pass
    except Exception as e:
        log.warning("subscribe_events error: %s", e)


# ─────────────────────────────────────────────────────────
# 6. GENERAL-PURPOSE HELPERS
# ─────────────────────────────────────────────────────────

async def incr_counter(key: str, ttl: int = 0) -> int:
    c = await get_client()
    if not c:
        return 0
    try:
        val = await c.incr(f"cvis:{key}")
        if ttl > 0 and val == 1:
            await c.expire(f"cvis:{key}", ttl)
        return val
    except Exception:
        return 0


async def redis_info() -> dict:
    c = await get_client()
    if not c:
        return {"available": False}
    try:
        info = await c.info("server")
        return {
            "available":    True,
            "redis_version": info.get("redis_version"),
            "uptime_s":     info.get("uptime_in_seconds"),
            "used_memory":  info.get("used_memory_human"),
        }
    except Exception:
        return {"available": False}
