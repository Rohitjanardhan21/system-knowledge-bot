import asyncio
import json

import pytest

from backend.core.devices import command_service as cs


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.expirations = {}
        self.streams = {}

    async def hset(self, key, *args, mapping=None):
        if key not in self.hashes:
            self.hashes[key] = {}

        if mapping is not None:
            self.hashes[key].update(mapping)
        elif len(args) == 2:
            self.hashes[key][args[0]] = args[1]

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def exists(self, key):
        return key in self.hashes

    async def eval(self, script, numkeys, *args):
        key = args[0]
        expected = args[1]
        new_status = args[2]

        data = self.hashes.get(key)
        if not data or data.get("status") != expected:
            return 0

        data["status"] = new_status
        return 1

    async def expire(self, key, ttl):
        self.expirations[key] = ttl
        return True

    async def xadd(self, key, fields):
        self.streams.setdefault(key, []).append(dict(fields))
        return f"{len(self.streams[key])}-0"

    async def xrevrange(self, key, count=None):
        entries = list(reversed(self.streams.get(key, [])))

        if count is not None:
            entries = entries[:count]

        return [
            (f"{index}-0", fields)
            for index, fields in enumerate(entries, start=1)
        ]

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def hset(self, key, *args, mapping=None):
        self.operations.append(("hset", key, args, mapping))
        return self

    def expire(self, key, ttl):
        self.operations.append(("expire", key, ttl))
        return self

    def xadd(self, key, fields):
        self.operations.append(("xadd", key, fields))
        return self

    async def execute(self):
        snapshot = (
            {k: dict(v) for k, v in self.redis.hashes.items()},
            dict(self.redis.expirations),
            {k: list(v) for k, v in self.redis.streams.items()},
        )

        try:
            results = []
            for op in self.operations:
                if op[0] == "hset":
                    _, key, args, mapping = op
                    await self.redis.hset(key, *args, mapping=mapping)
                    results.append(True)
                elif op[0] == "expire":
                    _, key, ttl = op
                    results.append(await self.redis.expire(key, ttl))
                elif op[0] == "xadd":
                    _, key, fields = op
                    results.append(await self.redis.xadd(key, fields))
            return results
        except Exception:
            self.redis.hashes = snapshot[0]
            self.redis.expirations = snapshot[1]
            self.redis.streams = snapshot[2]
            raise


def run(coro):
    return asyncio.run(coro)


def test_create_command_persists_state_and_enqueues():
    redis = FakeRedis()

    command = run(
        cs.create_command(
            redis,
            device_id="device-001",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    assert command["command_id"]
    assert command["device_id"] == "device-001"
    assert command["command_type"] == "diagnostic.health_check"
    assert command["status"] == "pending"

    state_key = f"{cs.COMMAND_STATE_PREFIX}{command['command_id']}"
    stream_key = f"{cs.COMMAND_STREAM_PREFIX}device-001"

    assert state_key in redis.hashes
    assert stream_key in redis.streams
    assert len(redis.streams[stream_key]) == 1

    stored = redis.hashes[state_key]

    assert stored["command_id"] == command["command_id"]
    assert stored["device_id"] == "device-001"
    assert stored["status"] == "pending"
    assert json.loads(stored["payload"]) == {}


def test_claim_next_command_claims_pending_command():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="device-claim-001",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    claimed = run(
        cs.claim_next_command(
            redis,
            "device-claim-001",
        )
    )

    assert claimed is not None
    assert claimed["command_id"] == created["command_id"]
    assert claimed["device_id"] == "device-claim-001"
    assert claimed["status"] == "acknowledged"

    loaded = run(
        cs.get_command(
            redis,
            created["command_id"],
        )
    )

    assert loaded["status"] == "acknowledged"


def test_claim_next_command_does_not_return_already_claimed_command():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="device-claim-002",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    first = run(
        cs.claim_next_command(
            redis,
            "device-claim-002",
        )
    )

    second = run(
        cs.claim_next_command(
            redis,
            "device-claim-002",
        )
    )

    assert first["command_id"] == created["command_id"]
    assert first["status"] == "acknowledged"
    assert second is None


def test_claim_next_command_expires_expired_command():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="device-claim-003",
            command_type="diagnostic.health_check",
            requested_by="controller",
            ttl_s=60,
        )
    )

    state_key = f"{cs.COMMAND_STATE_PREFIX}{created['command_id']}"
    redis.hashes[state_key]["expires_at"] = "0"

    claimed = run(
        cs.claim_next_command(
            redis,
            "device-claim-003",
        )
    )

    assert claimed is None

    loaded = run(
        cs.get_command(
            redis,
            created["command_id"],
        )
    )

    assert loaded["status"] == "expired"


def test_claim_next_command_does_not_cross_device_boundary():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="device-owner-001",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    claimed = run(
        cs.claim_next_command(
            redis,
            "device-other-001",
        )
    )

    assert claimed is None

    loaded = run(
        cs.get_command(
            redis,
            created["command_id"],
        )
    )

    assert loaded["device_id"] == "device-owner-001"
    assert loaded["status"] == "pending"


def test_create_command_preserves_payload():
    redis = FakeRedis()

    command = run(
        cs.create_command(
            redis,
            device_id="device-002",
            command_type="diagnostic.system_snapshot",
            requested_by="admin",
            payload={"include_processes": True},
        )
    )

    assert command["payload"] == {"include_processes": True}

    state_key = f"{cs.COMMAND_STATE_PREFIX}{command['command_id']}"
    stored = redis.hashes[state_key]

    assert json.loads(stored["payload"]) == {
        "include_processes": True
    }


def test_create_command_rejects_unknown_command():
    redis = FakeRedis()

    with pytest.raises(ValueError, match="Unsupported command type"):
        run(
            cs.create_command(
                redis,
                device_id="device-003",
                command_type="shell.exec",
                requested_by="admin",
            )
        )


def test_create_command_rejects_invalid_device():
    redis = FakeRedis()

    with pytest.raises(ValueError, match="Invalid device_id"):
        run(
            cs.create_command(
                redis,
                device_id="",
                command_type="diagnostic.health_check",
                requested_by="admin",
            )
        )


def test_create_command_rejects_missing_requester():
    redis = FakeRedis()

    with pytest.raises(ValueError, match="requested_by is required"):
        run(
            cs.create_command(
                redis,
                device_id="device-004",
                command_type="diagnostic.health_check",
                requested_by="",
            )
        )


def test_create_command_rejects_expired_ttl():
    redis = FakeRedis()

    with pytest.raises(ValueError, match="expiration must be in the future"):
        run(
            cs.create_command(
                redis,
                device_id="device-005",
                command_type="diagnostic.health_check",
                requested_by="admin",
                ttl_s=0,
            )
        )


def test_create_command_rejects_ttl_above_maximum():
    redis = FakeRedis()

    with pytest.raises(
        ValueError,
        match="exceeds maximum lifetime",
    ):
        run(
            cs.create_command(
                redis,
                device_id="device-006",
                command_type="diagnostic.health_check",
                requested_by="admin",
                ttl_s=cs.COMMAND_TTL_S + 1,
            )
        )


def test_get_command_round_trip():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="device-007",
            command_type="diagnostic.process_list",
            requested_by="admin",
            payload={"limit": 10},
        )
    )

    loaded = run(
        cs.get_command(
            redis,
            created["command_id"],
        )
    )

    assert loaded["command_id"] == created["command_id"]
    assert loaded["device_id"] == "device-007"
    assert loaded["command_type"] == "diagnostic.process_list"
    assert loaded["requested_by"] == "admin"
    assert loaded["payload"] == {"limit": 10}
    assert loaded["status"] == "pending"


def test_get_unknown_command_returns_none():
    redis = FakeRedis()

    assert run(
        cs.get_command(
            redis,
            "does-not-exist",
        )
    ) is None


def test_transition_existing_command():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="device-008",
            command_type="diagnostic.health_check",
            requested_by="admin",
        )
    )

    assert run(
        cs.transition_command(
            redis,
            created["command_id"],
            "acknowledged",
        )
    ) is True

    loaded = run(
        cs.get_command(
            redis,
            created["command_id"],
        )
    )

    assert loaded["status"] == "acknowledged"


def test_transition_unknown_command_returns_false():
    redis = FakeRedis()

    assert run(
        cs.transition_command(
            redis,
            "does-not-exist",
            "acknowledged",
        )
    ) is False


def test_transition_rejects_invalid_state():
    redis = FakeRedis()

    with pytest.raises(ValueError, match="Invalid command state"):
        run(
            cs.transition_command(
                redis,
                "does-not-exist",
                "running",
            )
        )


def test_legal_command_transitions():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="state-device-001",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    command_id = created["command_id"]

    assert run(
        cs.transition_command(redis, command_id, "acknowledged")
    ) is True

    assert run(
        cs.transition_command(redis, command_id, "executing")
    ) is True

    assert run(
        cs.transition_command(redis, command_id, "completed")
    ) is True

    loaded = run(cs.get_command(redis, command_id))
    assert loaded["status"] == "completed"


@pytest.mark.parametrize(
    ("current_status", "new_status"),
    [
        ("pending", "executing"),
        ("pending", "completed"),
        ("pending", "failed"),
        ("acknowledged", "completed"),
        ("acknowledged", "failed"),
        ("executing", "acknowledged"),
        ("executing", "pending"),
        ("completed", "pending"),
        ("completed", "failed"),
        ("failed", "pending"),
        ("expired", "pending"),
        ("expired", "executing"),
    ],
)
def test_illegal_command_transitions(
    current_status,
    new_status,
):
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="state-device-002",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    command_id = created["command_id"]

    if current_status != "pending":
        if current_status == "acknowledged":
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "acknowledged",
                )
            )
        elif current_status == "executing":
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "acknowledged",
                )
            )
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "executing",
                )
            )
        elif current_status == "completed":
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "acknowledged",
                )
            )
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "executing",
                )
            )
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "completed",
                )
            )
        elif current_status == "failed":
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "acknowledged",
                )
            )
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "executing",
                )
            )
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "failed",
                )
            )
        elif current_status == "expired":
            assert run(
                cs.transition_command(
                    redis,
                    command_id,
                    "expired",
                )
            )

    assert run(
        cs.transition_command(
            redis,
            command_id,
            new_status,
        )
    ) is False


def test_pending_can_expire():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="state-device-003",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    assert run(
        cs.transition_command(
            redis,
            created["command_id"],
            "expired",
        )
    ) is True


def test_acknowledged_can_expire():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="state-device-004",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    command_id = created["command_id"]

    assert run(
        cs.transition_command(
            redis,
            command_id,
            "acknowledged",
        )
    ) is True

    assert run(
        cs.transition_command(
            redis,
            command_id,
            "expired",
        )
    ) is True


def test_executing_can_fail():
    redis = FakeRedis()

    created = run(
        cs.create_command(
            redis,
            device_id="state-device-005",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    command_id = created["command_id"]

    assert run(
        cs.transition_command(
            redis,
            command_id,
            "acknowledged",
        )
    ) is True

    assert run(
        cs.transition_command(
            redis,
            command_id,
            "executing",
        )
    ) is True

    assert run(
        cs.transition_command(
            redis,
            command_id,
            "failed",
        )
    ) is True

def test_create_command_uses_requested_ttl():
    redis = FakeRedis()

    run(
        cs.create_command(
            redis,
            device_id="device-ttl",
            command_type="diagnostic.health_check",
            requested_by="controller",
            ttl_s=45,
        )
    )

    command_ids = list(redis.hashes.keys())
    state_key = next(
        key for key in command_ids
        if key.startswith(cs.COMMAND_STATE_PREFIX)
    )

    assert redis.expirations[state_key] == 45

class FailingXAddRedis(FakeRedis):
    async def xadd(self, key, fields):
        raise RuntimeError("stream unavailable")


def test_create_command_does_not_leave_state_when_delivery_fails():
    redis = FailingXAddRedis()

    with pytest.raises(RuntimeError, match="stream unavailable"):
        run(
            cs.create_command(
                redis,
                device_id="device-atomic",
                command_type="diagnostic.health_check",
                requested_by="controller",
            )
        )

    assert redis.hashes == {}
    assert redis.streams == {}

class TrackingRedis(FakeRedis):
    def __init__(self):
        super().__init__()
        self.eval_called = False

    async def eval(self, script, numkeys, *args):
        self.eval_called = True
        key = args[0]
        expected = args[1]
        new_status = args[2]

        data = self.hashes.get(key)
        if not data or data.get("status") != expected:
            return 0

        data["status"] = new_status
        return 1


def test_transition_command_uses_atomic_redis_operation():
    redis = TrackingRedis()

    command = run(
        cs.create_command(
            redis,
            device_id="device-cas",
            command_type="diagnostic.health_check",
            requested_by="controller",
        )
    )

    result = run(
        cs.transition_command(
            redis,
            command["command_id"],
            "acknowledged",
        )
    )

    assert result is True
    assert redis.eval_called is True
