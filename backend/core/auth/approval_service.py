"""Redis-backed, one-time approvals for destructive process actions."""

import math
import os
import secrets
import time

MAX_APPROVAL_TTL_S = 120.0
KEY_PREFIX = "process:approval:"
ALLOWED_ACTIONS = frozenset({
    "kill_high_cpu",
    "kill_process",
    "kill_high_cpu_process",
})

class SelfApprovalError(ValueError):
    """Raised when a requester attempts to approve their own request."""


def _redis_client():
    import redis

    return redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


def _identity(device_id, action, pid, create_time, name):
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("device_id is required")
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Action is not eligible for process approval")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("A positive PID is required")
    if isinstance(create_time, bool) or not isinstance(create_time, (int, float)):
        raise ValueError("A valid process creation time is required")
    if not math.isfinite(float(create_time)) or create_time <= 0:
        raise ValueError("A valid process creation time is required")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Exact process name is required")

    return {
        "device_id": device_id,
        "action": action,
        "pid": str(pid),
        "create_time": format(float(create_time), ".17g"),
        "name": name,
    }


def create_approval_request(
    *, requested_by, device_id, action, pid, create_time, name,
    ttl_s=60.0, client=None,
):
    """Create a pending request. Creating it does not authorize execution."""
    if not isinstance(requested_by, str) or not requested_by.strip():
        raise ValueError("requested_by is required")
    if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)):
        raise ValueError("Invalid approval lifetime")
    if not math.isfinite(float(ttl_s)) or not 0 < ttl_s <= MAX_APPROVAL_TTL_S:
        raise ValueError("Approval lifetime must be between 0 and 120 seconds")

    identity = _identity(device_id, action, pid, create_time, name)
    now = time.time()
    expires_at = now + float(ttl_s)
    approval_id = secrets.token_urlsafe(32)

    record = {
        **identity,
        "approval_id": approval_id,
        "requested_by": requested_by,
        "status": "pending",
        "created_at": format(now, ".17g"),
        "expires_at": format(expires_at, ".17g"),
    }

    redis_client = client if client is not None else _redis_client()
    pipe = redis_client.pipeline(transaction=True)
    pipe.hset(f"{KEY_PREFIX}{approval_id}", mapping=record)
    pipe.expire(f"{KEY_PREFIX}{approval_id}", math.ceil(float(ttl_s)))
    pipe.execute()

    return {
        "approval_id": approval_id,
        "status": "pending",
        "device_id": device_id,
        "action": action,
        "pid": pid,
        "create_time": float(create_time),
        "name": name,
        "requested_by": requested_by,
        "expires_at": expires_at,
    }


_DECIDE_SCRIPT = """
local status = redis.call('HGET', KEYS[1], 'status')
local expires = tonumber(redis.call('HGET', KEYS[1], 'expires_at') or '0')
local now = tonumber(ARGV[1])
if status ~= 'pending' or expires <= now then return 0 end
local requested_by = redis.call('HGET', KEYS[1], 'requested_by')
if ARGV[2] == 'approved' and requested_by == ARGV[3] then return -1 end
redis.call('HSET', KEYS[1],
    'status', ARGV[2], 'decided_by', ARGV[3], 'decided_at', ARGV[1])
return 1
"""


def decide_approval(approval_id, *, approved, decided_by, client=None):
    """Approve or reject a pending request exactly once."""
    if not isinstance(approval_id, str) or not approval_id:
        return False
    if type(approved) is not bool:
        raise ValueError("approved must be a boolean")
    if not isinstance(decided_by, str) or not decided_by.strip():
        raise ValueError("decided_by is required")

    redis_client = client if client is not None else _redis_client()
    result = redis_client.eval(
        _DECIDE_SCRIPT,
        1,
        f"{KEY_PREFIX}{approval_id}",
        format(time.time(), ".17g"),
        "approved" if approved else "rejected",
        decided_by,
    )
    if result == -1:
        raise SelfApprovalError("The requester cannot approve their own request")
    return result == 1


_CONSUME_SCRIPT = """
local status = redis.call('HGET', KEYS[1], 'status')
local expires = tonumber(redis.call('HGET', KEYS[1], 'expires_at') or '0')
local now = tonumber(ARGV[1])
if status ~= 'approved' or expires <= now then return 0 end
local fields = {'device_id', 'action', 'pid', 'create_time', 'name'}
for i, field in ipairs(fields) do
    local actual = redis.call('HGET', KEYS[1], field)
    if not actual or actual ~= ARGV[i + 1] then return 0 end
end
redis.call('HSET', KEYS[1], 'status', 'consumed', 'consumed_at', ARGV[1])
return 1
"""


def consume_approval(
    approval_id, *, device_id, action, pid, create_time, name, client=None
):
    """Atomically consume a matching, approved, unexpired approval."""
    if not isinstance(approval_id, str) or not approval_id:
        return False

    identity = _identity(device_id, action, pid, create_time, name)
    redis_client = client if client is not None else _redis_client()

    return redis_client.eval(
        _CONSUME_SCRIPT,
        1,
        f"{KEY_PREFIX}{approval_id}",
        format(time.time(), ".17g"),
        identity["device_id"],
        identity["action"],
        identity["pid"],
        identity["create_time"],
        identity["name"],
    ) == 1
