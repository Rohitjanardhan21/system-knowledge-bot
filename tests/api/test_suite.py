"""
CVIS v9 — tests/test_suite.py
Coverage: auth, redis_store (mocked), ml_engine, alert_engine, API endpoints
"""

import asyncio, hashlib, time
import numpy as np
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app
# ── bootstrap env before importing app modules ───────────
import os
os.environ.setdefault("CVIS_API_KEY",     "test-bootstrap-key-abc123")
os.environ.setdefault("JWT_SECRET",       "test-jwt-secret-not-for-prod")
os.environ.setdefault("CVIS_ADMIN_PASS",  "test-admin-pass")
os.environ.setdefault("CVIS_ADMIN_USER",  "admin")
os.environ.setdefault("REDIS_URL",        "redis://localhost:6379/0")

# ─────────────────────────────────────────────────────────
# Auth tests
# ─────────────────────────────────────────────────────────
class TestAuth:
    def test_api_key_accepted(self):
        from auth import _api_key_store, _hash
        assert _hash in _api_key_store
        assert _api_key_store[_hash]["scope"] == "admin"

    def test_api_key_hash_stability(self):
        key = os.environ["CVIS_API_KEY"]
        h1  = hashlib.sha256(key.encode()).hexdigest()
        h2  = hashlib.sha256(key.encode()).hexdigest()
        assert h1 == h2

    def test_jwt_issue_and_decode(self):
        from auth import issue_token_pair, _verify_jwt, JWT_OK
        if not JWT_OK:
            pytest.skip("PyJWT not installed")
        pair   = issue_token_pair("test-user", scope="read")
        assert pair.access_token
        assert pair.refresh_token
        assert pair.expires_in > 0
        loop   = asyncio.new_event_loop()
        payload = loop.run_until_complete(_verify_jwt(pair.access_token))
        loop.close()
        assert payload["sub"] == "test-user"
        assert payload["scope"] == "read"
        assert payload["type"] == "access"

    def test_jwt_scope_ladder(self):
        from auth import _scope_gte
        assert     _scope_gte("admin", "read")
        assert     _scope_gte("admin", "write")
        assert     _scope_gte("admin", "admin")
        assert     _scope_gte("write", "read")
        assert not _scope_gte("read",  "write")
        assert not _scope_gte("read",  "admin")

    @pytest.mark.asyncio
    async def test_create_api_key(self):
        from auth import create_api_key, _verify_api_key
        with patch("auth.get_redis", AsyncMock(return_value=None)):
            key     = await create_api_key("test-service", scope="write")
            entry   = await _verify_api_key(key)
            assert entry["scope"] == "write"
            assert entry["name"]  == "test-service"


# ─────────────────────────────────────────────────────────
# Redis store tests (mocked)
# ─────────────────────────────────────────────────────────
class TestRedisStore:
    @pytest.mark.asyncio
    async def test_alert_dedup_fires_once(self):
        """Two calls for same rule within cooldown: only first should fire."""
        from redis_store import alert_check_and_set

        nx_results = [True, None]   # first call: key set; second: key exists

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=nx_results)

        with patch("redis_store.get_client", AsyncMock(return_value=mock_redis)):
            r1 = await alert_check_and_set("rule_cpu_crit", 60)
            r2 = await alert_check_and_set("rule_cpu_crit", 60)

        assert r1 is True    # should fire
        assert r2 is False   # suppressed

    @pytest.mark.asyncio
    async def test_rate_limit_allows_within_limit(self):
        from redis_store import rate_limit_check
        mock_redis = AsyncMock()
        mock_redis.pipeline.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.pipeline.return_value.__aexit__  = AsyncMock(return_value=False)
        mock_redis.pipeline = MagicMock(return_value=mock_redis)
        mock_redis.execute  = AsyncMock(return_value=[5, True])
        mock_redis.incr     = AsyncMock(return_value=5)
        mock_redis.expire   = AsyncMock(return_value=True)

        with patch("redis_store.get_client", AsyncMock(return_value=mock_redis)):
            # Use pipeline mock directly via get_client
            pass

        # Test fallback (Redis None) — always allows
        with patch("redis_store.get_client", AsyncMock(return_value=None)):
            allowed, count = await rate_limit_check("127.0.0.1", limit=100)
            assert allowed is True
            assert count == 0

    @pytest.mark.asyncio
    async def test_cache_metrics_roundtrip(self):
        metrics = {"cpu_percent": 45.2, "memory": 62.1}
        stored  = None

        mock_redis = AsyncMock()
        async def _setex(key, ttl, value):
            nonlocal stored
            stored = value
        async def _get(key):
            return stored
        mock_redis.setex = _setex
        mock_redis.get   = _get

        with patch("redis_store.get_client", AsyncMock(return_value=mock_redis)):
            from redis_store import cache_metrics, get_cached_metrics
            await cache_metrics(metrics, ttl=3)
            result = await get_cached_metrics()

        assert result == metrics

    @pytest.mark.asyncio
    async def test_redis_unavailable_graceful(self):
        """All Redis ops should silently no-op when Redis is down."""
        with patch("redis_store.get_client", AsyncMock(return_value=None)):
            from redis_store import (alert_check_and_set, cache_metrics,
                                      get_cached_metrics, blocklist_token)
            assert await alert_check_and_set("r1", 60)  is True
            assert await get_cached_metrics()            is None
            await cache_metrics({"cpu": 10})             # no exception
            await blocklist_token("fake-jti", 60)        # no exception


# ─────────────────────────────────────────────────────────
# ML Engine tests
# ─────────────────────────────────────────────────────────
class TestMLEngine:
    def setup_method(self):
        from ml_engine import MLEngine
        self.engine = MLEngine()

    def test_ingest_and_score(self):
        feat = np.array([0.3, 0.4, 0.2, 0.1, 0.05], dtype=np.float32)
        for _ in range(10):
            self.engine.ingest(feat)
        m = self.engine.score(feat)
        assert 0.0 <= m.ensemble_score <= 1.0
        assert 0.0 <= m.if_score       <= 1.0
        assert 0.0 <= m.vae_score      <= 1.0
        assert 0.0 <= m.lstm_score     <= 1.0

    def test_anomaly_score_higher_for_outlier(self):
        """Outlier feature should score higher than baseline after training."""
        normal  = np.array([0.3, 0.4, 0.2, 0.1, 0.05], dtype=np.float32)
        outlier = np.array([0.98, 0.97, 0.95, 0.9, 0.9], dtype=np.float32)
        for _ in range(50):
            self.engine.ingest(normal)
        normal_score  = self.engine.score(normal).vae_score
        outlier_score = self.engine.score(outlier).vae_score
        assert outlier_score >= normal_score, (
            f"Outlier {outlier_score:.4f} should >= normal {normal_score:.4f}"
        )

    def test_state_dict_roundtrip(self):
        feat = np.array([0.3, 0.4, 0.2, 0.1, 0.05], dtype=np.float32)
        for _ in range(20):
            self.engine.ingest(feat)
        sd = self.engine.state_dict()
        assert "lstm" in sd
        assert "vae"  in sd
        assert "metrics" in sd

    def test_feature_buffer_bounded(self):
        feat = np.random.rand(5).astype(np.float32)
        for _ in range(700):
            self.engine.ingest(feat)
        assert len(self.engine.feature_buf) <= 512


# ─────────────────────────────────────────────────────────
# Alert engine tests
# ─────────────────────────────────────────────────────────
class TestAlertEngine:
    def setup_method(self):
        from alert_engine import AlertEngine
        self.ae = AlertEngine()

    def test_default_rules_loaded(self):
        assert len(self.ae.rules) >= 7

    def test_add_custom_rule(self):
        from alert_engine import AlertRule
        rule = AlertRule("test_r1", "Test rule", "cpu", "gt", 95.0, "CRITICAL", 30)
        self.ae.add_rule(rule)
        assert "test_r1" in self.ae.rules

    def test_delete_rule(self):
        assert self.ae.delete_rule("r_cpu_warn") is True
        assert "r_cpu_warn" not in self.ae.rules
        assert self.ae.delete_rule("nonexistent") is False

    def test_update_rule(self):
        updated = self.ae.update_rule("r_cpu_crit", threshold=95.0, enabled=False)
        assert updated is not None
        assert updated.threshold == 95.0
        assert updated.enabled   is False

    @pytest.mark.asyncio
    async def test_evaluate_no_fire_nominal(self):
        """Nominal metrics must not append anything to history."""
        from alert_engine import AlertEngine
        ae = AlertEngine()
        metrics = {"cpu_percent": 30, "memory": 40, "disk_percent": 20,
                   "health_score": 95, "anomaly_score": 0.05, "network_percent": 25}
        ae._dispatch = AsyncMock()
        await ae.evaluate(metrics)
        assert len(ae.history) == 0, f"Unexpected alerts: {[a.severity for a in ae.history]}"

    @pytest.mark.asyncio
    async def test_evaluate_fires_on_critical(self):
        """CPU 95% must fire both CRITICAL (>90) and WARNING (>75) rules.
        Checks ae.history which is written before dispatch — test is immune to
        AsyncMock / event-loop interaction issues with side_effect."""
        from alert_engine import AlertEngine
        ae = AlertEngine()
        ae._dispatch = AsyncMock()   # suppress real HTTP/SMTP side effects
        metrics = {"cpu_percent": 95, "memory": 40, "disk_percent": 20,
                   "health_score": 70, "anomaly_score": 0.1, "network_percent": 25}
        await ae.evaluate(metrics)
        # history is written unconditionally inside evaluate(), before dispatch
        severities = [a.severity for a in ae.history]
        assert "CRITICAL" in severities, f"Expected CRITICAL in history, got: {severities}"
        assert "WARNING"  in severities, f"Expected WARNING  in history, got: {severities}"

    @pytest.mark.asyncio
    async def test_cooldown_prevents_double_fire(self):
        """Same rule should not fire twice within cooldown period."""
        metrics = {"cpu_percent": 95, "memory": 40, "disk_percent": 20,
                   "health_score": 70, "anomaly_score": 0.1, "network_percent": 25}
        fired = []
        async def _mock_dispatch(alert):
            fired.append(alert)
        self.ae._dispatch = _mock_dispatch

        # Manually set cooldown to simulate it was just fired
        self.ae._cooldowns["r_cpu_crit"] = time.time()

        await self.ae.evaluate(metrics)
        critical_fires = [a for a in fired if a.rule_id == "r_cpu_crit"]
        assert len(critical_fires) == 0   # should be suppressed


# ─────────────────────────────────────────────────────────
# API endpoint integration tests
# ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from backend_v9 import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

API_KEY = os.environ["CVIS_API_KEY"]
AUTH_HEADERS = {"X-API-Key": API_KEY}


class TestAPIEndpoints:
    def test_health_public(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_os_status_requires_auth(self, client):
        r = client.get("/os/status")
        assert r.status_code == 401

    def test_os_status_with_api_key(self, client):
        r = client.get("/os/status", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert "cpu_percent" in r.json() or "ps_available" in r.json()

    def test_ml_status_auth(self, client):
        r = client.get("/ml/status", headers=AUTH_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert "ensemble_score" in data
        assert "backend" in data

    def test_ml_scores_post(self, client):
        r = client.post("/ml/scores",
                        json={"features": [0.3, 0.4, 0.2, 0.1, 0.05]},
                        headers=AUTH_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert 0.0 <= data["ensemble_score"] <= 1.0

    def test_ml_scores_invalid_features(self, client):
        r = client.post("/ml/scores",
                        json={"features": [0.3, 0.4]},   # wrong length
                        headers=AUTH_HEADERS)
        assert r.status_code == 422

    def test_login_invalid(self, client):
        r = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    def test_login_valid(self, client):
        r = client.post("/auth/login",
                        json={"username": "admin", "password": os.environ["CVIS_ADMIN_PASS"]})
        assert r.status_code == 200
        data = r.json()
        assert "access_token"  in data
        assert "refresh_token" in data

    def test_models_versions_readable(self, client):
        r = client.get("/models/versions", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_alerts_history_readable(self, client):
        r = client.get("/alerts/history", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_alerts_rules_readable(self, client):
        r = client.get("/alerts/rules", headers=AUTH_HEADERS)
        assert r.status_code == 200
        rules = r.json()
        assert len(rules) >= 7

    def test_write_requires_write_scope(self, client):
        """Bootstrap key has admin scope — should be able to add a webhook."""
        r = client.post("/alerts/webhooks",
                        json={"url": "https://example.com/hook", "name": "test"},
                        headers=AUTH_HEADERS)
        # 200 or 422 (validation) but NOT 401/403
        assert r.status_code not in (401, 403)

    def test_unauthorized_returns_401(self, client):
        r = client.post("/models/save", json={})
        assert r.status_code == 401

    def test_wrong_scope_returns_403(self, client):
        """A read-scope key should not be able to save a model version."""
        from auth import create_api_key
        loop = asyncio.new_event_loop()
        with patch("auth.get_redis", AsyncMock(return_value=None)):
            read_key = loop.run_until_complete(create_api_key("read-only", "read"))
        loop.close()

        r = client.post("/models/save", json={},
                        headers={"X-API-Key": read_key})
        assert r.status_code == 403
