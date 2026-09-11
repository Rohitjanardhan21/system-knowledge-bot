import asyncio
import time

import pytest

import backend.main as main


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def eval(self, script, numkeys, key, timestamp, ttl):
        current = self.values.get(key)

        if current is not None and float(timestamp) <= float(current):
            return 0

        self.values[key] = timestamp
        return 1

    async def hset(self, key, mapping):
        return 1


def run(coro):
    return asyncio.run(coro)


def test_heartbeat_accepts_new_timestamp(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(main, "get_redis", lambda: asyncio.sleep(0, result=redis))

    device_id = "heartbeat-test-001"
    timestamp = time.time()

    assert run(main._accept_heartbeat_timestamp(device_id, timestamp)) is True


def test_heartbeat_rejects_replay(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(main, "get_redis", lambda: asyncio.sleep(0, result=redis))

    device_id = "heartbeat-test-002"
    timestamp = time.time()

    assert run(main._accept_heartbeat_timestamp(device_id, timestamp)) is True
    assert run(main._accept_heartbeat_timestamp(device_id, timestamp)) is False


def test_heartbeat_rejects_out_of_order_timestamp(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(main, "get_redis", lambda: asyncio.sleep(0, result=redis))

    device_id = "heartbeat-test-003"
    newer = time.time()
    older = newer - 1

    assert run(main._accept_heartbeat_timestamp(device_id, newer)) is True
    assert run(main._accept_heartbeat_timestamp(device_id, older)) is False


def test_heartbeat_endpoint_updates_registered_device(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(main, "get_redis", lambda: asyncio.sleep(0, result=redis))

    device_id = "heartbeat-test-004"
    main._devices[device_id] = {
        "device_id": device_id,
        "device_name": "Heartbeat Test",
        "os": "linux",
        "hostname": "heartbeat-host",
        "status": "offline",
        "last_seen": None,
        "metrics": {},
        "processes": [],
    }

    principal = {"device_id": device_id, "scope": "write"}
    payload = main.DeviceHeartbeatPayload(
        device_id=device_id,
        timestamp=time.time(),
    )

    result = run(
        main.receive_device_heartbeat(
            device_id=device_id,
            payload=payload,
            principal=principal,
        )
    )

    assert result["status"] == "online"
    assert result["device_id"] == device_id
    assert main._devices[device_id]["status"] == "online"
    assert main._devices[device_id]["last_seen"] is not None

    del main._devices[device_id]


def test_heartbeat_rejects_wrong_device():
    device_id = "heartbeat-test-005"

    payload = main.DeviceHeartbeatPayload(
        device_id=device_id,
        timestamp=time.time(),
    )

    with pytest.raises(main.HTTPException) as exc:
        run(
            main.receive_device_heartbeat(
                device_id=device_id,
                payload=payload,
                principal={"device_id": "different-device", "scope": "write"},
            )
        )

    assert exc.value.status_code == 403


def test_heartbeat_rejects_payload_device_mismatch():
    device_id = "heartbeat-test-006"

    payload = main.DeviceHeartbeatPayload(
        device_id="different-device",
        timestamp=time.time(),
    )

    with pytest.raises(main.HTTPException) as exc:
        run(
            main.receive_device_heartbeat(
                device_id=device_id,
                payload=payload,
                principal={"device_id": device_id, "scope": "write"},
            )
        )

    assert exc.value.status_code == 400


def test_heartbeat_rejects_stale_timestamp():
    device_id = "heartbeat-test-007"

    payload = main.DeviceHeartbeatPayload(
        device_id=device_id,
        timestamp=time.time() - main.HEARTBEAT_MAX_AGE_S - 1,
    )

    with pytest.raises(main.HTTPException) as exc:
        run(
            main.receive_device_heartbeat(
                device_id=device_id,
                payload=payload,
                principal={"device_id": device_id, "scope": "write"},
            )
        )

    assert exc.value.status_code == 409


def test_heartbeat_rejects_future_timestamp():
    device_id = "heartbeat-test-008"

    payload = main.DeviceHeartbeatPayload(
        device_id=device_id,
        timestamp=time.time() + main.HEARTBEAT_MAX_FUTURE_SKEW_S + 1,
    )

    with pytest.raises(main.HTTPException) as exc:
        run(
            main.receive_device_heartbeat(
                device_id=device_id,
                payload=payload,
                principal={"device_id": device_id, "scope": "write"},
            )
        )

    assert exc.value.status_code == 409


def test_heartbeat_requires_registered_device(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(main, "get_redis", lambda: asyncio.sleep(0, result=redis))

    device_id = "heartbeat-test-unregistered"

    main._devices.pop(device_id, None)

    payload = main.DeviceHeartbeatPayload(
        device_id=device_id,
        timestamp=time.time(),
    )

    with pytest.raises(main.HTTPException) as exc:
        run(
            main.receive_device_heartbeat(
                device_id=device_id,
                payload=payload,
                principal={"device_id": device_id, "scope": "write"},
            )
        )

    assert exc.value.status_code == 404
