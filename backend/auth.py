"""Admin authentication.

The app is public. Predictions and the read-only views are for everyone; anything
that can change the model or the data belongs to the operator. Before this module
existed there were five unauthenticated mutating endpoints, including one that let
any caller overwrite a prediction's actual score — which falsifies the accuracy
figures the dashboard reports.

Credentials come from the environment, not the database, and that is deliberate:
the free host has no persistent disk, so an accounts table would be silently reset
to whatever was baked into the seed snapshot on every restart. Admins created after
a deploy would simply vanish. Environment variables survive restarts and redeploys,
and the password never exists in the repository — only its scrypt hash, generated
locally by scripts/make-admin-hash.py.

Two ways to authenticate, because there are two kinds of caller:
  - a signed session cookie, for a person using the admin UI
  - an `X-Admin-Key` header, for the scheduled refresh workflow, which cannot
    hold a cookie
"""
from __future__ import annotations

import hashlib
import os
import secrets

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

COOKIE_NAME = "epl_admin"
SESSION_MAX_AGE = 12 * 60 * 60          # 12 hours
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def is_configured() -> bool:
    """True only if a login could actually succeed."""
    return bool(_env("ADMIN_USERNAME") and _env("ADMIN_PASSWORD_HASH") and _env("SESSION_SECRET"))


# ---------------------------------------------------------------- passwords

def hash_password(password: str, salt: bytes | None = None) -> str:
    """`scrypt$<salt-hex>$<hash-hex>`.

    scrypt from the standard library rather than a bcrypt dependency: it is a
    memory-hard KDF, it ships with Python, and it keeps the deployed image from
    growing for one function.
    """
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verification. Any malformed hash is a failure, never a pass."""
    try:
        scheme, salt_hex, digest_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex),
            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=len(expected),
        )
    except (ValueError, AttributeError):
        return False
    # compare_digest, not ==, so a wrong password cannot be found byte by byte
    # from response timing.
    return secrets.compare_digest(actual, expected)


# ---------------------------------------------------------------- sessions

def _signer() -> TimestampSigner:
    secret = _env("SESSION_SECRET")
    if not secret:
        # Never fall back to a default or generated secret. A per-process random
        # secret would "work" while quietly invalidating every session on restart,
        # and a hardcoded one would let anyone who has read this file mint a
        # session on your deployment.
        raise HTTPException(status_code=503, detail="Admin auth is not configured on this server.")
    return TimestampSigner(secret, salt="epl-admin-session")


def issue_session(username: str) -> str:
    return _signer().sign(username.encode()).decode()


def read_session(token: str) -> str | None:
    """Return the username a token attests to, or None if it does not hold up."""
    try:
        return _signer().unsign(token, max_age=SESSION_MAX_AGE).decode()
    except (BadSignature, SignatureExpired, HTTPException):
        return None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=SESSION_MAX_AGE,
        # httponly: a cross-site scripting bug cannot read this cookie out, which
        # it could if the token lived in localStorage.
        httponly=True,
        # The API is reached same-origin through the frontend's /api rewrite, so
        # lax is sufficient and avoids the cross-site pitfalls of `none`.
        samesite="lax",
        # Off for local http development; on everywhere it is served over https.
        secure=_env("COOKIE_SECURE").lower() not in ("0", "false", "no"),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


# ---------------------------------------------------------------- dependency

def current_admin(request: Request) -> str | None:
    """The signed-in admin, or None. Never raises — for optional-auth callers."""
    api_key = _env("ADMIN_API_KEY")
    presented = request.headers.get("X-Admin-Key")
    if api_key and presented and secrets.compare_digest(presented, api_key):
        return "api-key"

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return read_session(token)
    except HTTPException:
        return None


def require_admin(request: Request) -> str:
    """Gate for every endpoint that can change the model or the data.

    Fails closed. If the server has no admin configured, this raises 503 rather
    than letting the request through — a missing secret must never be read as
    "no authentication required".
    """
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="Admin auth is not configured on this server, so admin actions are disabled.",
        )
    admin = current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Admin authentication required.")
    return admin


AdminUser = Depends(require_admin)
