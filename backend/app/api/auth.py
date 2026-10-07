"""Small, database-backed authentication API using stdlib cryptography."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr

from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str
    user_id: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str | None = None


def _db():
    if not (settings.use_postgres and settings.database_url.startswith("postgres")):
        raise HTTPException(503, "Authentication requires PostgreSQL")
    try:
        import psycopg
    except ImportError as exc:
        raise HTTPException(503, "PostgreSQL driver is not installed") from exc
    return psycopg.connect(settings.database_url, autocommit=True)


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    rounds = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return (
        f"pbkdf2_sha256${rounds}"
        f"${base64.urlsafe_b64encode(salt).decode()}"
        f"${base64.urlsafe_b64encode(digest).decode()}"
    )


def _verify(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.urlsafe_b64decode(salt), int(rounds)
        )
        return hmac.compare_digest(base64.urlsafe_b64encode(actual).decode(), expected)
    except (ValueError, TypeError):
        return False


def _issue(auth_id: str, user_id: str | None) -> TokenResponse:
    ttl = settings.access_token_ttl_minutes * 60
    token_id = secrets.token_urlsafe(24)
    payload = {"jti": token_id, "sub": auth_id, "uid": user_id, "exp": int(datetime.now(timezone.utc).timestamp()) + ttl}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    secret = settings.signing_secret.encode()
    token = body + "." + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    with _db() as conn:
        conn.execute(
            "INSERT INTO auth_sessions (auth_id, token_hash, expires_at) VALUES (%s, %s, now() + make_interval(mins => %s))",
            (auth_id, hashlib.sha256(token.encode()).hexdigest(), settings.access_token_ttl_minutes),
        )
    return TokenResponse(access_token=token, expires_in=ttl, user_id=user_id)


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    token = authorization.split(" ", 1)[1]
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(settings.signing_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, json.JSONDecodeError, UnicodeError):
        raise HTTPException(401, "Invalid token") from None
    if payload.get("exp", 0) < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(401, "Token expired")
    with _db() as conn:
        row = conn.execute(
            "SELECT auth_id, user_id FROM auth_users JOIN auth_sessions USING (auth_id) "
            "WHERE auth_id = %s AND token_hash = %s AND revoked_at IS NULL AND expires_at > now()",
            (payload.get("sub"), hashlib.sha256(token.encode()).hexdigest()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Session revoked or unknown")
    return {"auth_id": str(row[0]), "user_id": row[1]}


@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(credentials: Credentials):
    if len(credentials.password) < settings.password_min_length:
        raise HTTPException(400, f"Password must be at least {settings.password_min_length} characters")
    with _db() as conn:
        try:
            row = conn.execute(
                "INSERT INTO auth_users (email, password_hash, user_id) VALUES (%s, %s, %s) RETURNING auth_id, user_id",
                (str(credentials.email).lower(), _password_hash(credentials.password), credentials.user_id),
            ).fetchone()
        except Exception as exc:
            if "auth_users_email_key" in str(exc) or "unique" in str(exc).lower():
                raise HTTPException(409, "Email already registered") from exc
            raise
    return _issue(str(row[0]), row[1])


@router.post("/login", response_model=TokenResponse)
def login(credentials: Credentials):
    with _db() as conn:
        row = conn.execute(
            "SELECT auth_id, user_id, password_hash FROM auth_users WHERE email = %s",
            (str(credentials.email).lower(),),
        ).fetchone()
    if not row or not _verify(credentials.password, row[2]):
        raise HTTPException(401, "Invalid email or password")
    return _issue(str(row[0]), row[1])


@router.post("/logout", status_code=204)
def logout(user: dict = Depends(current_user), authorization: str = Header(...)):
    token = authorization.split(" ", 1)[1]
    with _db() as conn:
        conn.execute("UPDATE auth_sessions SET revoked_at = now() WHERE token_hash = %s",
                     (hashlib.sha256(token.encode()).hexdigest(),))


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user

