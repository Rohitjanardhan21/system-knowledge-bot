"""
Distributed device command service.

This module owns command creation and durable command state.
It does not execute commands.

Transport:
    Redis Streams

State:
    Redis hashes

Safety:
    - explicit command allowlist
    - device binding
    - command expiration
    - unique command IDs
"""

import json
import time
import uuid
from typing import Any


COMMAND_STREAM_PREFIX = "device:commands:"
COMMAND_STATE_PREFIX = "device:command:"
COMMAND_TTL_S = 300.0

ALLOWED_COMMANDS = frozenset(
    {
        "diagnostic.health_check",
        "diagnostic.system_snapshot",
        "diagnostic.process_list",
    }
)

VALID_STATES = frozenset(
    {
        "pending",
        "acknowledged",
        "executing",
        "completed",
        "failed",
        "expired",
    }
)


def _command_key(command_id: str) -> str:
    return f"{COMMAND_STATE_PREFIX}{command_id}"


def _stream_key(device_id: str) -> str:
    return f"{COMMAND_STREAM_PREFIX}{device_id}"


def _validate_command_type(command_type: str) -> None:
    if command_type not in ALLOWED_COMMANDS:
        raise ValueError(f"Unsupported command type: {command_type}")


def _validate_device_id(device_id: str) -> None:
    if not device_id or len(device_id) > 128:
        raise ValueError("Invalid device_id")


def _validate_ttl(expires_at: float, now: float) -> None:
    if expires_at <= now:
        raise ValueError("Command expiration must be in the future")

    if expires_at - now > COMMAND_TTL_S:
        raise ValueError("Command expiration exceeds maximum lifetime")


async def create_command(
    redis,
    *,
    device_id: str,
    command_type: str,
    requested_by: str,
    payload: dict[str, Any] | None = None,
    ttl_s: float = COMMAND_TTL_S,
) -> dict[str, Any]:
    """
    Create a durable device command and enqueue it for delivery.

    The command state is stored in a Redis hash and the delivery
    event is appended to a per-device Redis Stream.
    """
    _validate_device_id(device_id)
    _validate_command_type(command_type)

    if not requested_by:
        raise ValueError("requested_by is required")

    now = time.time()
    expires_at = now + float(ttl_s)
    _validate_ttl(expires_at, now)

    command_id = uuid.uuid4().hex

    command = {
        "command_id": command_id,
        "device_id": device_id,
        "command_type": command_type,
        "requested_by": requested_by,
        "payload": payload or {},
        "status": "pending",
        "created_at": now,
        "expires_at": expires_at,
    }

    state_key = _command_key(command_id)
    stream_key = _stream_key(device_id)

    pipe = redis.pipeline()

    pipe.hset(
        state_key,
        mapping={
            "command_id": command_id,
            "device_id": device_id,
            "command_type": command_type,
            "requested_by": requested_by,
            "payload": json.dumps(command["payload"]),
            "status": "pending",
            "created_at": str(now),
            "expires_at": str(expires_at),
        },
    )

    pipe.expire(state_key, int(ttl_s))

    pipe.xadd(
        stream_key,
        {
            "command_id": command_id,
            "command_type": command_type,
            "expires_at": str(expires_at),
        },
    )

    await pipe.execute()

    return command


async def get_command(redis, command_id: str) -> dict[str, Any] | None:
    """Return the durable command state."""
    if not command_id:
        return None

    data = await redis.hgetall(_command_key(command_id))

    if not data:
        return None

    try:
        payload = json.loads(data.get("payload", "{}"))
    except (TypeError, ValueError):
        payload = {}

    return {
        "command_id": data.get("command_id", command_id),
        "device_id": data.get("device_id"),
        "command_type": data.get("command_type"),
        "requested_by": data.get("requested_by"),
        "payload": payload,
        "status": data.get("status"),
        "created_at": float(data["created_at"])
        if data.get("created_at")
        else None,
        "expires_at": float(data["expires_at"])
        if data.get("expires_at")
        else None,
    }


COMMAND_TRANSITIONS = {
    "pending": frozenset({"acknowledged", "expired"}),
    "acknowledged": frozenset({"executing", "expired"}),
    "executing": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "expired": frozenset(),
}


async def transition_command(
    redis,
    command_id: str,
    new_status: str,
) -> bool:
    """
    Transition a command through its allowed lifecycle.

    Returns False when the command does not exist or the requested
    transition is not legal.
    """
    if new_status not in VALID_STATES:
        raise ValueError(f"Invalid command state: {new_status}")

    key = _command_key(command_id)

    # Redis-side compare-and-set. The current status is read and
    # validated together with the write, preventing concurrent
    # workers from both transitioning the same command.
    transition_script = """
    local current = redis.call('HGET', KEYS[1], 'status')
    if not current then
        return 0
    end

    local expected = ARGV[1]
    local target = ARGV[2]

    if current ~= expected then
        return 0
    end

    redis.call('HSET', KEYS[1], 'status', target)
    return 1
    """

    # Determine the currently legal predecessor statuses. The actual
    # check/write is performed atomically by Redis.
    for current_status, allowed_targets in COMMAND_TRANSITIONS.items():
        if new_status not in allowed_targets:
            continue

        result = await redis.eval(
            transition_script,
            1,
            key,
            current_status,
            new_status,
        )

        if result:
            return True

    return False
