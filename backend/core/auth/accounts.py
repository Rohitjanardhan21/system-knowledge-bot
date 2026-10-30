"""Persistence and email verification for personal CVIS accounts."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from email.utils import parseaddr
from pathlib import Path

import aiosqlite
import asyncpg
import httpx
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.core.storage.db import DB_PATH

VERIFICATION_TTL_SECONDS = 60 * 60
PASSWORD_RESET_TTL_SECONDS = 60 * 60
_PASSWORD_SCRYPT_N = 1 << 14
_PASSWORD_SCRYPT_R = 8
_PASSWORD_SCRYPT_P = 1
_PASSWORD_DKLEN = 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS personal_users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    email_verified_at REAL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS personal_workspaces (
    workspace_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL UNIQUE REFERENCES personal_users(user_id),
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES personal_users(user_id) ON DELETE CASCADE,
    expires_at REAL NOT NULL,
    consumed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_email_verification_user
ON email_verification_tokens(user_id, expires_at DESC);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES personal_users(user_id) ON DELETE CASCADE,
    expires_at REAL NOT NULL,
    consumed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_password_reset_user
ON password_reset_tokens(user_id, expires_at DESC);
"""


def normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    _, parsed_address = parseaddr(normalized)
    if (
        len(normalized) > 254
        or parsed_address != normalized
        or normalized.count("@") != 1
        or any(character.isspace() for character in normalized)
    ):
        raise ValueError("Enter a valid email address.")
    local, domain = normalized.rsplit("@", 1)
    if (
        not local
        or len(local) > 64
        or not domain
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
    ):
        raise ValueError("Enter a valid email address.")
    return normalized


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_PASSWORD_SCRYPT_N,
        r=_PASSWORD_SCRYPT_R,
        p=_PASSWORD_SCRYPT_P,
        dklen=_PASSWORD_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _PASSWORD_SCRYPT_N,
        _PASSWORD_SCRYPT_R,
        _PASSWORD_SCRYPT_P,
        salt.hex(),
        digest.hex(),
    )


_DUMMY_PASSWORD_HASH = _hash_password(secrets.token_urlsafe(32))


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        n_value, r_value, p_value = int(n), int(r), int(p)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        if (
            n_value != _PASSWORD_SCRYPT_N
            or r_value != _PASSWORD_SCRYPT_R
            or p_value != _PASSWORD_SCRYPT_P
            or len(salt) != 16
            or len(expected) != _PASSWORD_DKLEN
        ):
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n_value,
            r=r_value,
            p=p_value,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, MemoryError):
        return False


async def _connect() -> aiosqlite.Connection:
    database_path = Path(DB_PATH)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = await aiosqlite.connect(str(database_path), timeout=10)
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await connection.executescript(_SCHEMA)
    return connection



_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS personal_users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email_verified_at DOUBLE PRECISION,
    created_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS personal_workspaces (
    workspace_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL UNIQUE REFERENCES personal_users(user_id),
    name TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES personal_users(user_id) ON DELETE CASCADE,
    expires_at DOUBLE PRECISION NOT NULL,
    consumed_at DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_email_verification_user
ON email_verification_tokens(user_id, expires_at DESC);
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES personal_users(user_id) ON DELETE CASCADE,
    expires_at DOUBLE PRECISION NOT NULL,
    consumed_at DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_password_reset_user
ON password_reset_tokens(user_id, expires_at DESC);
"""


def _postgres_dsn() -> str | None:
    """Return a normalized DSN; never log the credential-bearing URL."""
    raw = os.environ.get("CVIS_DATABASE_URL", "").strip()
    if not raw:
        if os.environ.get("ENV", "").strip().lower() in {"prod", "production"}:
            raise RuntimeError("CVIS_DATABASE_URL must be configured in production.")
        return None
    try:
        parts = urlsplit(raw)
        hostname = parts.hostname
        database_name = parts.path.strip("/")
        parts.port
    except ValueError as exc:
        raise RuntimeError("CVIS_DATABASE_URL is invalid.") from exc
    scheme = "postgresql" if parts.scheme in {"postgres", "postgresql+asyncpg"} else parts.scheme
    if scheme != "postgresql" or not hostname or not database_name:
        raise RuntimeError("CVIS_DATABASE_URL must be a valid PostgreSQL connection URL.")
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key.lower() not in {"sslmode", "ssl"}]
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _postgres_ssl_mode() -> str:
    raw = os.environ.get("CVIS_DATABASE_URL", "").strip()
    if not raw:
        return "require"
    query = {
        key.lower(): value
        for key, value in parse_qsl(
            urlsplit(raw).query,
            keep_blank_values=True,
        )
    }
    mode = query.get("sslmode", query.get("ssl", "require")).lower()
    if mode not in {
        "disable", "allow", "prefer", "require",
        "verify-ca", "verify-full",
    }:
        raise RuntimeError(
            "Unsupported PostgreSQL SSL mode in CVIS_DATABASE_URL."
        )
    if (
        os.environ.get("ENV", "").strip().lower() in {"prod", "production"}
        and mode not in {"require", "verify-ca", "verify-full"}
    ):
        raise RuntimeError("PostgreSQL TLS must be enabled in production.")
    return mode


async def _pg_connect():
    dsn = _postgres_dsn()
    if not dsn:
        raise RuntimeError("CVIS_DATABASE_URL is not configured.")
    connection = await asyncpg.connect(dsn=dsn, ssl=_postgres_ssl_mode(), timeout=10)
    try:
        await connection.execute(_PG_SCHEMA)
    except Exception:
        await connection.close()
        raise
    return connection


async def _pg_create_pending_account(email: str, password_hash: str, verification_base_url: str) -> None:
    user_id, workspace_id = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    token, now = secrets.token_urlsafe(32), time.time()
    connection = await _pg_connect()
    try:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO personal_users (user_id,email,password_hash,created_at) VALUES ($1,$2,$3,$4)",
                user_id, email, password_hash, now)
            await connection.execute(
                "INSERT INTO personal_workspaces (workspace_id,owner_user_id,name,created_at) VALUES ($1,$2,$3,$4)",
                workspace_id, user_id, "Personal workspace", now)
            await connection.execute(
                "INSERT INTO email_verification_tokens (token_hash,user_id,expires_at) VALUES ($1,$2,$3)",
                _verification_token_hash(token), user_id, now + VERIFICATION_TTL_SECONDS)
    except asyncpg.UniqueViolationError as exc:
        raise ValueError("An account with this email already exists.") from exc
    finally:
        await connection.close()
    await asyncio.to_thread(_send_verification_email, email, build_verification_url(verification_base_url, token))


async def _pg_authenticate_personal_user(email: str, password: str) -> dict | None:
    connection = await _pg_connect()
    try:
        user = await connection.fetchrow(
            """
            SELECT u.user_id, u.email, u.password_hash, u.email_verified_at,
                   w.workspace_id
            FROM personal_users AS u
            JOIN personal_workspaces AS w ON w.owner_user_id = u.user_id
            WHERE u.email = $1
            """,
            email,
        )
    finally:
        await connection.close()
    if user is None:
        await asyncio.to_thread(verify_password, password, _DUMMY_PASSWORD_HASH)
        return None
    if not await asyncio.to_thread(verify_password, password, user["password_hash"]):
        return None
    if user["email_verified_at"] is None:
        raise PermissionError("Verify your email before signing in.")
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "workspace_id": user["workspace_id"],
    }


async def _pg_verify_email_token(token: str) -> None:
    token_hash, now = _verification_token_hash(token), time.time()
    connection = await _pg_connect()
    try:
        async with connection.transaction():
            row = await connection.fetchrow(
                "SELECT user_id FROM email_verification_tokens WHERE token_hash=$1 AND consumed_at IS NULL AND expires_at > $2 FOR UPDATE",
                token_hash, now)
            if row is None:
                raise ValueError("This verification link is invalid or has expired.")
            await connection.execute(
                "UPDATE personal_users SET email_verified_at=COALESCE(email_verified_at,$1) WHERE user_id=$2",
                now, row["user_id"])
            await connection.execute(
                "UPDATE email_verification_tokens SET consumed_at=$1 WHERE token_hash=$2 AND consumed_at IS NULL",
                now, token_hash)
    finally:
        await connection.close()


async def _pg_issue_verification_for_pending_email(email: str, verification_base_url: str) -> bool:
    token, now = secrets.token_urlsafe(32), time.time()
    connection = await _pg_connect()
    try:
        async with connection.transaction():
            user = await connection.fetchrow(
                "SELECT user_id FROM personal_users WHERE email=$1 AND email_verified_at IS NULL FOR UPDATE", email)
            if user is None:
                return False
            await connection.execute(
                "UPDATE email_verification_tokens SET consumed_at=$1 WHERE user_id=$2 AND consumed_at IS NULL",
                now, user["user_id"])
            await connection.execute(
                "INSERT INTO email_verification_tokens (token_hash,user_id,expires_at) VALUES ($1,$2,$3)",
                _verification_token_hash(token), user["user_id"], now + VERIFICATION_TTL_SECONDS)
    finally:
        await connection.close()
    await asyncio.to_thread(_send_verification_email, email, build_verification_url(verification_base_url, token))
    return True


async def _pg_issue_password_reset(email: str, password_reset_base_url: str) -> bool:
    token, now = secrets.token_urlsafe(32), time.time()
    connection = await _pg_connect()
    try:
        async with connection.transaction():
            user = await connection.fetchrow(
                "SELECT user_id FROM personal_users WHERE email=$1",
                email,
            )
            if user is None:
                return False
            await connection.execute(
                "UPDATE password_reset_tokens SET consumed_at=$1 WHERE user_id=$2 AND consumed_at IS NULL",
                now,
                user["user_id"],
            )
            await connection.execute(
                "INSERT INTO password_reset_tokens (token_hash,user_id,expires_at) VALUES ($1,$2,$3)",
                _verification_token_hash(token),
                user["user_id"],
                now + PASSWORD_RESET_TTL_SECONDS,
            )
    finally:
        await connection.close()
    await asyncio.to_thread(
        _send_password_reset_email,
        email,
        build_password_reset_url(password_reset_base_url, token),
    )
    return True

def _verification_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_verification_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/#verify-email={token}"


def build_password_reset_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/#reset-password={token}"


def ensure_email_delivery_configured() -> None:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get(
        "EMAIL_FROM", "CVIS <onboarding@resend.dev>"
    ).strip()
    if not api_key:
        raise RuntimeError(
            "Email verification requires the RESEND_API_KEY environment variable."
        )
    if not sender or "@" not in sender:
        raise RuntimeError(
            "Email verification requires a valid EMAIL_FROM sender address."
        )


def _send_verification_email(email: str, verification_url: str) -> None:
    ensure_email_delivery_configured()
    api_key = os.environ["RESEND_API_KEY"].strip()
    sender = os.environ.get(
        "EMAIL_FROM", "CVIS <onboarding@resend.dev>"
    ).strip()
    payload = {
        "from": sender,
        "to": [email],
        "subject": "Verify your CVIS account",
        "text": (
            "Verify your CVIS personal account by opening this link:\n\n"
            f"{verification_url}\n\n"
            "This link expires in one hour. If you did not request this account, "
            "you can ignore this message."
        ),
    }
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Could not deliver the verification email through Resend."
        ) from exc


def _send_password_reset_email(email: str, reset_url: str) -> None:
    ensure_email_delivery_configured()
    api_key = os.environ["RESEND_API_KEY"].strip()
    sender = os.environ.get(
        "EMAIL_FROM", "CVIS <onboarding@resend.dev>"
    ).strip()
    payload = {
        "from": sender,
        "to": [email],
        "subject": "Reset your CVIS password",
        "text": (
            "Reset your CVIS personal account password by opening this link:\n\n"
            f"{reset_url}\n\n"
            "This link expires in one hour. If you did not request a reset, "
            "you can ignore this message."
        ),
    }
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Could not deliver the password reset email through Resend."
        ) from exc


async def issue_password_reset(email: str, password_reset_base_url: str) -> bool:
    normalized_email = normalize_email(email)
    if _postgres_dsn():
        return await _pg_issue_password_reset(
            normalized_email,
            password_reset_base_url,
        )

    token, now = secrets.token_urlsafe(32), time.time()
    connection = await _connect()
    try:
        async with connection.execute(
            "SELECT user_id FROM personal_users WHERE email = ?",
            (normalized_email,),
        ) as cursor:
            user = await cursor.fetchone()
        if user is None:
            return False
        await connection.execute("BEGIN IMMEDIATE")
        await connection.execute(
            """
            UPDATE password_reset_tokens
            SET consumed_at = ?
            WHERE user_id = ? AND consumed_at IS NULL
            """,
            (now, user["user_id"]),
        )
        await connection.execute(
            """
            INSERT INTO password_reset_tokens (token_hash, user_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (
                _verification_token_hash(token),
                user["user_id"],
                now + PASSWORD_RESET_TTL_SECONDS,
            ),
        )
        await connection.commit()
    except Exception:
        await connection.rollback()
        raise
    finally:
        await connection.close()
    await asyncio.to_thread(
        _send_password_reset_email,
        normalized_email,
        build_password_reset_url(password_reset_base_url, token),
    )
    return True


async def _pg_reset_password(token: str, password: str) -> None:
    token_hash, now = _verification_token_hash(token), time.time()
    password_hash = await asyncio.to_thread(_hash_password, password)
    connection = await _pg_connect()
    try:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                SELECT user_id FROM password_reset_tokens
                WHERE token_hash=$1 AND consumed_at IS NULL AND expires_at > $2
                FOR UPDATE
                """,
                token_hash,
                now,
            )
            if row is None:
                raise ValueError("This password reset link is invalid or has expired.")
            await connection.execute(
                "UPDATE personal_users SET password_hash=$1 WHERE user_id=$2",
                password_hash,
                row["user_id"],
            )
            await connection.execute(
                "UPDATE password_reset_tokens SET consumed_at=$1 WHERE token_hash=$2 AND consumed_at IS NULL",
                now,
                token_hash,
            )
    finally:
        await connection.close()


async def reset_password(token: str, password: str) -> None:
    if not token or len(token) > 256:
        raise ValueError("This password reset link is invalid or has expired.")
    if _postgres_dsn():
        await _pg_reset_password(token, password)
        return

    token_hash, now = _verification_token_hash(token), time.time()
    password_hash = await asyncio.to_thread(_hash_password, password)
    connection = await _connect()
    try:
        await connection.execute("BEGIN IMMEDIATE")
        async with connection.execute(
            """
            SELECT user_id FROM password_reset_tokens
            WHERE token_hash = ? AND consumed_at IS NULL AND expires_at > ?
            """,
            (token_hash, now),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            await connection.rollback()
            raise ValueError("This password reset link is invalid or has expired.")
        await connection.execute(
            "UPDATE personal_users SET password_hash = ? WHERE user_id = ?",
            (password_hash, row["user_id"]),
        )
        await connection.execute(
            """
            UPDATE password_reset_tokens SET consumed_at = ?
            WHERE token_hash = ? AND consumed_at IS NULL
            """,
            (now, token_hash),
        )
        await connection.commit()
    except Exception:
        await connection.rollback()
        raise
    finally:
        await connection.close()


async def create_pending_account(
    email: str,
    password: str,
    verification_base_url: str,
) -> None:
    if _postgres_dsn():
        normalized_email = normalize_email(email)
        ensure_email_delivery_configured()
        password_hash = await asyncio.to_thread(_hash_password, password)
        await _pg_create_pending_account(normalized_email, password_hash, verification_base_url)
        return

    normalized_email = normalize_email(email)
    password_hash = await asyncio.to_thread(_hash_password, password)
    user_id = secrets.token_urlsafe(24)
    workspace_id = secrets.token_urlsafe(24)
    token = secrets.token_urlsafe(32)
    now = time.time()

    connection = await _connect()
    try:
        await connection.execute("BEGIN IMMEDIATE")
        await connection.execute(
            """
            INSERT INTO personal_users (user_id, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, normalized_email, password_hash, now),
        )
        await connection.execute(
            """
            INSERT INTO personal_workspaces (workspace_id, owner_user_id, name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (workspace_id, user_id, "Personal workspace", now),
        )
        await connection.execute(
            """
            INSERT INTO email_verification_tokens (token_hash, user_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (_verification_token_hash(token), user_id, now + VERIFICATION_TTL_SECONDS),
        )
        await connection.commit()
    except sqlite3.IntegrityError as exc:
        await connection.rollback()
        raise ValueError("An account with this email already exists.") from exc
    except Exception:
        await connection.rollback()
        raise
    finally:
        await connection.close()

    verification_url = build_verification_url(verification_base_url, token)
    await asyncio.to_thread(_send_verification_email, normalized_email, verification_url)


async def authenticate_personal_user(email: str, password: str) -> dict | None:
    if _postgres_dsn():
        try:
            normalized_email = normalize_email(email)
        except ValueError:
            await asyncio.to_thread(verify_password, password, _DUMMY_PASSWORD_HASH)
            return None
        return await _pg_authenticate_personal_user(normalized_email, password)

    try:
        normalized_email = normalize_email(email)
    except ValueError:
        return None

    connection = await _connect()
    try:
        async with connection.execute(
            """
            SELECT u.user_id, u.email, u.password_hash, u.email_verified_at,
                   w.workspace_id
            FROM personal_users AS u
            JOIN personal_workspaces AS w ON w.owner_user_id = u.user_id
            WHERE u.email = ?
            """,
            (normalized_email,),
        ) as cursor:
            user = await cursor.fetchone()
    finally:
        await connection.close()

    if user is None:
        await asyncio.to_thread(verify_password, password, _DUMMY_PASSWORD_HASH)
        return None
    password_is_valid = await asyncio.to_thread(
        verify_password, password, user["password_hash"]
    )
    if not password_is_valid:
        return None
    if user["email_verified_at"] is None:
        raise PermissionError("Verify your email before signing in.")
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "workspace_id": user["workspace_id"],
    }


async def verify_email_token(token: str) -> None:
    if _postgres_dsn():
        if not token or len(token) > 256:
            raise ValueError("This verification link is invalid or has expired.")
        await _pg_verify_email_token(token)
        return

    if not token or len(token) > 256:
        raise ValueError("This verification link is invalid or has expired.")
    token_hash = _verification_token_hash(token)
    connection = await _connect()
    try:
        await connection.execute("BEGIN IMMEDIATE")
        async with connection.execute(
            """
            SELECT user_id
            FROM email_verification_tokens
            WHERE token_hash = ? AND consumed_at IS NULL AND expires_at > ?
            """,
            (token_hash, time.time()),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            await connection.rollback()
            raise ValueError("This verification link is invalid or has expired.")
        await connection.execute(
            """
            UPDATE personal_users SET email_verified_at = ?
            WHERE user_id = ? AND email_verified_at IS NULL
            """,
            (time.time(), row["user_id"]),
        )
        await connection.execute(
            """
            UPDATE email_verification_tokens SET consumed_at = ?
            WHERE token_hash = ? AND consumed_at IS NULL
            """,
            (time.time(), token_hash),
        )
        await connection.commit()
    except Exception:
        await connection.rollback()
        raise
    finally:
        await connection.close()


async def issue_verification_for_pending_email(
    email: str,
    verification_base_url: str,
) -> bool:
    if _postgres_dsn():
        try:
            normalized_email = normalize_email(email)
        except ValueError:
            return False
        return await _pg_issue_verification_for_pending_email(normalized_email, verification_base_url)

    normalized_email = normalize_email(email)
    connection = await _connect()
    try:
        async with connection.execute(
            """
            SELECT user_id FROM personal_users
            WHERE email = ? AND email_verified_at IS NULL
            """,
            (normalized_email,),
        ) as cursor:
            user = await cursor.fetchone()
        if user is None:
            return False

        token = secrets.token_urlsafe(32)
        now = time.time()
        await connection.execute(
            """
            UPDATE email_verification_tokens
            SET consumed_at = ?
            WHERE user_id = ? AND consumed_at IS NULL
            """,
            (now, user["user_id"]),
        )
        await connection.execute(
            """
            INSERT INTO email_verification_tokens (token_hash, user_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (
                _verification_token_hash(token),
                user["user_id"],
                now + VERIFICATION_TTL_SECONDS,
            ),
        )
        await connection.commit()
    finally:
        await connection.close()

    await asyncio.to_thread(
        _send_verification_email,
        normalized_email,
        build_verification_url(verification_base_url, token),
    )
    return True
