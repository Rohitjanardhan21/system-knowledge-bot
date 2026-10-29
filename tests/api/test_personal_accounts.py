from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.core.auth import accounts
from backend.core.auth import auth as auth_module


@pytest.fixture
def client():
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def account_environment(tmp_path, monkeypatch):
    database_path = tmp_path / "accounts.db"
    sent_emails = []
    monkeypatch.setattr(accounts, "DB_PATH", str(database_path))
    monkeypatch.delenv("CVIS_DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "settings_path", lambda: None)
    monkeypatch.setattr(main, "_enforce_auth_rate_limit", AsyncMock())
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://cvis.example.test")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("EMAIL_FROM", "CVIS <onboarding@resend.dev>")
    monkeypatch.setattr(
        accounts,
        "_send_verification_email",
        lambda email, url: sent_emails.append((email, url)),
    )
    return database_path, sent_emails


def _registration_payload(email="User@example.test", password="correct-horse-battery"):
    return {"email": email, "password": password}


def _token_from_email(sent_emails, index=0):
    return parse_qs(urlsplit(sent_emails[index][1]).fragment)["verify-email"][0]


def _reset_token_from_email(sent_emails, index=0):
    return parse_qs(urlsplit(sent_emails[index][1]).fragment)["reset-password"][0]


def test_personal_registration_sends_verification_link_and_stores_only_password_hash(
    client, account_environment
):
    database_path, sent_emails = account_environment

    response = client.post("/auth/register", json=_registration_payload())

    assert response.status_code == 202
    assert response.json()["message"].startswith("Account created")
    assert sent_emails[0][0] == "user@example.test"
    assert sent_emails[0][1].startswith("https://cvis.example.test/#verify-email=")
    with sqlite3.connect(database_path) as database:
        user = database.execute(
            "SELECT email, password_hash, email_verified_at FROM personal_users"
        ).fetchone()
        workspace_count = database.execute(
            "SELECT COUNT(*) FROM personal_workspaces"
        ).fetchone()[0]
        token_hash = database.execute(
            "SELECT token_hash FROM email_verification_tokens"
        ).fetchone()[0]

    assert user[0] == "user@example.test"
    assert user[1].startswith("scrypt$")
    assert user[1] != _registration_payload()["password"]
    assert user[2] is None
    assert workspace_count == 1
    assert token_hash == hashlib.sha256(_token_from_email(sent_emails).encode()).hexdigest()


def test_personal_account_requires_single_use_email_verification_before_login(
    client, account_environment
):
    _, sent_emails = account_environment
    assert client.post("/auth/register", json=_registration_payload()).status_code == 202
    login_payload = {
        "username": "user@example.test",
        "password": _registration_payload()["password"],
    }

    before_verification = client.post("/auth/login", json=login_payload)
    assert before_verification.status_code == 403
    assert "Verify your email" in before_verification.json()["detail"]

    token = _token_from_email(sent_emails)
    verified = client.post("/auth/verify-email", json={"token": token})
    assert verified.status_code == 200

    login = client.post("/auth/login", json=login_payload)
    assert login.status_code == 200
    claims = auth_module._jwt.decode(
        login.json()["access_token"],
        auth_module.JWT_SECRET,
        algorithms=[auth_module.JWT_ALGORITHM],
    )
    assert claims["scope"] == "read"
    assert claims["type"] == "access"

    reused_token = client.post("/auth/verify-email", json={"token": token})
    assert reused_token.status_code == 400


def test_personal_registration_rejects_duplicate_email(client, account_environment):
    client.post("/auth/register", json=_registration_payload())

    duplicate = client.post(
        "/auth/register",
        json=_registration_payload(email="USER@example.test"),
    )

    assert duplicate.status_code == 409


@pytest.mark.parametrize("email", ["not-an-email", "user@localhost", "user name@example.test"])
def test_personal_registration_rejects_malformed_email(
    client, account_environment, email
):
    response = client.post("/auth/register", json=_registration_payload(email=email))

    assert response.status_code == 422


def test_concurrent_duplicate_registrations_create_one_account(account_environment):
    async def create_accounts():
        async def create_account():
            try:
                await accounts.create_pending_account(
                    "race@example.test",
                    "correct-horse-battery",
                    "https://cvis.example.test",
                )
            except Exception as error:
                return error
            return None

        return await asyncio.gather(create_account(), create_account())

    outcomes = asyncio.run(create_accounts())

    assert sum(isinstance(outcome, ValueError) for outcome in outcomes) == 1
    assert sum(outcome is None for outcome in outcomes) == 1


def test_personal_account_routes_return_controlled_errors_when_database_is_unavailable(
    client, account_environment, monkeypatch
):
    async def unavailable_connection():
        raise sqlite3.OperationalError("private database details")

    monkeypatch.setattr(accounts, "_connect", unavailable_connection)
    responses = [
        client.post("/auth/register", json=_registration_payload()),
        client.post("/auth/resend-verification", json={"email": "user@example.test"}),
        client.post("/auth/verify-email", json={"token": "test-token"}),
        client.post(
            "/auth/login",
            json={"username": "user@example.test", "password": "correct-horse-battery"},
        ),
    ]

    assert [response.status_code for response in responses] == [503, 503, 503, 503]
    assert all("private database details" not in response.text for response in responses)


def test_registration_fails_explicitly_when_resend_is_not_configured(
    client, account_environment, monkeypatch
):
    database_path, _ = account_environment
    monkeypatch.delenv("RESEND_API_KEY")

    response = client.post("/auth/register", json=_registration_payload())

    assert response.status_code == 503
    assert "RESEND_API_KEY" in response.json()["detail"]
    assert not database_path.exists()


def test_production_requires_explicit_resend_configuration(
    client, account_environment, monkeypatch
):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CVIS_DATABASE_URL", "postgresql://user:pass@db.example.test/accounts")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        accounts.ensure_email_delivery_configured()


def test_registration_resend_failure_leaves_account_resendable(
    client, account_environment, monkeypatch
):
    database_path, sent_emails = account_environment

    def fail_delivery(email, url):
        raise RuntimeError("delivery failed")

    monkeypatch.setattr(accounts, "_send_verification_email", fail_delivery)
    failed_registration = client.post("/auth/register", json=_registration_payload())

    assert failed_registration.status_code == 503
    assert "delivery failed" not in failed_registration.text
    with sqlite3.connect(database_path) as database:
        assert database.execute(
            "SELECT email_verified_at FROM personal_users WHERE email = ?",
            ("user@example.test",),
        ).fetchone()[0] is None

    monkeypatch.setattr(
        accounts,
        "_send_verification_email",
        lambda email, url: sent_emails.append((email, url)),
    )
    resend = client.post(
        "/auth/resend-verification",
        json={"email": "user@example.test"},
    )

    assert resend.status_code == 200
    assert sent_emails[0][0] == "user@example.test"


def test_password_reset_changes_password_and_consumes_token(
    client, account_environment, monkeypatch
):
    _, sent_emails = account_environment
    reset_emails = []
    monkeypatch.setattr(
        accounts,
        "_send_password_reset_email",
        lambda email, url: reset_emails.append((email, url)),
    )
    assert client.post("/auth/register", json=_registration_payload()).status_code == 202
    verification_token = _token_from_email(sent_emails)
    assert client.post(
        "/auth/verify-email",
        json={"token": verification_token},
    ).status_code == 200

    requested = client.post(
        "/auth/password-reset/request",
        json={"email": "user@example.test"},
    )
    assert requested.status_code == 202
    assert reset_emails[0][0] == "user@example.test"

    reset_token = _reset_token_from_email(reset_emails)
    completed = client.post(
        "/auth/password-reset/complete",
        json={"token": reset_token, "password": "new-correct-password"},
    )
    assert completed.status_code == 200
    assert client.post(
        "/auth/login",
        json={
            "username": "user@example.test",
            "password": "correct-horse-battery",
        },
    ).status_code == 401
    assert client.post(
        "/auth/login",
        json={
            "username": "user@example.test",
            "password": "new-correct-password",
        },
    ).status_code == 200
    reused = client.post(
        "/auth/password-reset/complete",
        json={"token": reset_token, "password": "another-password"},
    )
    assert reused.status_code == 400


def test_password_reset_request_does_not_reveal_unknown_email(
    client, account_environment, monkeypatch
):
    reset_email = Mock()
    monkeypatch.setattr(accounts, "_send_password_reset_email", reset_email)

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "unknown@example.test"},
    )

    assert response.status_code == 202
    assert "If an account exists" in response.json()["message"]
    reset_email.assert_not_called()


def test_logout_route_revokes_submitted_tokens(client, monkeypatch):
    revoked_tokens = []

    async def revoke_token(token):
        revoked_tokens.append(token)

    monkeypatch.setattr(main, "revoke_token", revoke_token)

    response = client.post(
        "/auth/logout",
        json={"refresh_token": "refresh-token", "access_token": "access-token"},
    )

    assert response.status_code == 200
    assert revoked_tokens == ["refresh-token", "access-token"]


def test_production_requires_postgres_for_personal_account_routes(
    client, account_environment, monkeypatch
):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("CVIS_DATABASE_URL", raising=False)

    registration = client.post("/auth/register", json=_registration_payload())
    resend = client.post(
        "/auth/resend-verification",
        json={"email": "user@example.test"},
    )
    verification = client.post("/auth/verify-email", json={"token": "test-token"})
    login_response = client.post(
        "/auth/login",
        json={"username": "user@example.test", "password": "correct-horse-battery"},
    )

    assert [
        registration.status_code,
        resend.status_code,
        verification.status_code,
        login_response.status_code,
    ] == [503, 503, 503, 503]
    assert "CVIS_DATABASE_URL" not in registration.text


def test_production_postgres_requires_tls(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv(
        "CVIS_DATABASE_URL",
        "postgresql://user:password@db.example.test/accounts?sslmode=disable",
    )

    with pytest.raises(RuntimeError, match="TLS must be enabled"):
        accounts._postgres_ssl_mode()


def test_production_rejects_malformed_postgres_url(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CVIS_DATABASE_URL", "not-a-postgres-url")

    with pytest.raises(RuntimeError, match="valid PostgreSQL"):
        accounts._postgres_dsn()


def test_auth_rate_limit_uses_independent_ip_and_identity_buckets(monkeypatch):
    redis = AsyncMock()
    redis.eval.return_value = 1
    monkeypatch.setattr(main, "get_redis", AsyncMock(return_value=redis))
    request = Mock()
    request.client.host = "203.0.113.8"

    asyncio.run(
        main._enforce_auth_rate_limit(
            request,
            "register",
            limit=5,
            window_seconds=60,
            identity="first@example.test",
        )
    )
    first_ip_key = redis.eval.call_args_list[0].args[2]
    first_identity_key = redis.eval.call_args_list[1].args[2]
    redis.eval.reset_mock()

    asyncio.run(
        main._enforce_auth_rate_limit(
            request,
            "register",
            limit=5,
            window_seconds=60,
            identity="second@example.test",
        )
    )

    second_ip_key = redis.eval.call_args_list[0].args[2]
    second_identity_key = redis.eval.call_args_list[1].args[2]
    assert first_ip_key == second_ip_key
    assert first_identity_key != second_identity_key


def test_auth_rate_limit_fails_closed_when_redis_errors(monkeypatch):
    redis = AsyncMock()
    redis.eval.side_effect = RuntimeError("redis unavailable")
    monkeypatch.setattr(main, "get_redis", AsyncMock(return_value=redis))
    request = Mock()
    request.client.host = "203.0.113.8"

    with pytest.raises(main.HTTPException) as error:
        asyncio.run(
            main._enforce_auth_rate_limit(
                request,
                "register",
                limit=5,
                window_seconds=60,
                identity="user@example.test",
            )
        )

    assert error.value.status_code == 503


def test_verification_email_uses_resend_and_correct_recipient(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("EMAIL_FROM", "CVIS <onboarding@resend.dev>")
    response = Mock()
    response.raise_for_status = Mock()
    post = Mock(return_value=response)
    monkeypatch.setattr(accounts.httpx, "post", post)
    accounts._send_verification_email(
        "new-user@example.test",
        "https://cvis.example.test/#verify-email=token",
    )
    post.assert_called_once()
    args = post.call_args
    assert args.args[0] == "https://api.resend.com/emails"
    assert args.kwargs["headers"]["Authorization"] == "Bearer re_test_key"
    assert args.kwargs["json"]["to"] == ["new-user@example.test"]
    assert args.kwargs["json"]["from"] == "CVIS <onboarding@resend.dev>"
    assert "verify-email=token" in args.kwargs["json"]["text"]
    response.raise_for_status.assert_called_once()


def test_registration_is_disabled_for_local_desktop_backend(
    client, account_environment, monkeypatch
):
    monkeypatch.setattr(main, "settings_path", lambda: "C:/CVIS/settings.json")

    response = client.post("/auth/register", json=_registration_payload())

    assert response.status_code == 404


def test_resend_rotates_pending_verification_token(client, account_environment):
    _, sent_emails = account_environment
    client.post("/auth/register", json=_registration_payload())
    original_token = _token_from_email(sent_emails)

    response = client.post(
        "/auth/resend-verification",
        json={"email": "USER@example.test"},
    )

    assert response.status_code == 200
    new_token = _token_from_email(sent_emails, 1)
    assert new_token != original_token
    assert client.post(
        "/auth/verify-email",
        json={"token": original_token},
    ).status_code == 400
    assert client.post(
        "/auth/verify-email",
        json={"token": new_token},
    ).status_code == 200


def test_expired_verification_token_is_rejected(account_environment):
    database_path, sent_emails = account_environment

    async def expire_and_verify_token():
        await accounts.create_pending_account(
            "expired@example.test",
            "correct-horse-battery",
            "https://cvis.example.test",
        )
        token = _token_from_email(sent_emails)

        connection = await accounts._connect()
        try:
            await connection.execute(
                """
                UPDATE email_verification_tokens
                SET expires_at = 1
                WHERE token_hash = ?
                """,
                (accounts._verification_token_hash(token),),
            )
            await connection.commit()
        finally:
            await connection.close()

        with pytest.raises(ValueError, match="invalid or has expired"):
            await accounts.verify_email_token(token)

    asyncio.run(expire_and_verify_token())

    with sqlite3.connect(database_path) as database:
        assert database.execute(
            "SELECT email_verified_at FROM personal_users WHERE email = ?",
            ("expired@example.test",),
        ).fetchone()[0] is None


def test_existing_admin_login_keeps_admin_scope(client, monkeypatch):
    monkeypatch.setattr(main, "_USERS", {"admin-user": "admin-password"})

    response = client.post(
        "/auth/login",
        json={"username": "admin-user", "password": "admin-password"},
    )

    assert response.status_code == 200
    claims = auth_module._jwt.decode(
        response.json()["access_token"],
        auth_module.JWT_SECRET,
        algorithms=[auth_module.JWT_ALGORITHM],
    )
    assert claims["scope"] == "admin"


def test_registration_returns_429_when_rate_limit_is_exceeded(
    client, account_environment, monkeypatch
):
    async def reject_request(*args, **kwargs):
        raise main.HTTPException(status_code=429, detail="Too many requests")

    monkeypatch.setattr(main, "_enforce_auth_rate_limit", reject_request)
    response = client.post(
        "/auth/register",
        json=_registration_payload(),
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many requests"


def test_resend_verification_returns_429_when_rate_limit_is_exceeded(
    client, account_environment, monkeypatch
):
    async def reject_request(*args, **kwargs):
        raise main.HTTPException(status_code=429, detail="Too many requests")

    monkeypatch.setattr(main, "_enforce_auth_rate_limit", reject_request)
    response = client.post(
        "/auth/resend-verification",
        json={"email": "user@example.test"},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many requests"


def test_auth_rate_limit_rejects_request_above_limit(monkeypatch):
    redis = AsyncMock()
    redis.eval.side_effect = [1, 6]
    monkeypatch.setattr(main, "get_redis", AsyncMock(return_value=redis))
    request = Mock()
    request.client.host = "203.0.113.10"

    with pytest.raises(main.HTTPException) as error:
        asyncio.run(
            main._enforce_auth_rate_limit(
                request,
                "register",
                limit=5,
                window_seconds=3600,
                identity="user@example.test",
            )
        )

    assert error.value.status_code == 429
    assert redis.eval.await_count == 2


def test_auth_rate_limit_allows_request_at_limit(monkeypatch):
    redis = AsyncMock()
    redis.eval.side_effect = [5, 5]
    monkeypatch.setattr(main, "get_redis", AsyncMock(return_value=redis))
    request = Mock()
    request.client.host = "203.0.113.11"

    asyncio.run(
        main._enforce_auth_rate_limit(
            request,
            "register",
            limit=5,
            window_seconds=3600,
            identity="user@example.test",
        )
    )

    assert redis.eval.await_count == 2


def test_auth_rate_limit_lua_script_increments_and_sets_expiry(monkeypatch):
    redis = AsyncMock()
    redis.eval.return_value = 1
    monkeypatch.setattr(main, "get_redis", AsyncMock(return_value=redis))
    request = Mock()
    request.client.host = "203.0.113.20"

    asyncio.run(
        main._enforce_auth_rate_limit(
            request,
            "register",
            limit=5,
            window_seconds=3600,
            identity="user@example.test",
        )
    )

    assert redis.eval.await_count == 2
    for call in redis.eval.await_args_list:
        script, key_count, key, expiry = call.args
        assert key_count == 1
        assert key.startswith("cvis:auth:register:")
        assert expiry == 3600
        assert "INCR" in script
        assert "EXPIRE" in script
