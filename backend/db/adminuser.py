"""Reading and changing the operator account.

The bootstrap rule is the important part of this module, so it is stated once,
here, and enforced in one function:

    If `admin_users` is EMPTY, one row is created from ADMIN_USERNAME and
    ADMIN_PASSWORD_HASH. If it is NOT empty, the environment is ignored.

Without the second half, every deploy would quietly overwrite a changed password
with whatever the env var still said — the exact failure that moving credentials
into the database was meant to prevent. The consequence is worth knowing: once the
row exists, editing ADMIN_PASSWORD_HASH in Render has no effect. Break-glass is
documented in docs/DEPLOYMENT.md.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from db.database import AdminUser, SessionLocal

RESET_TTL_MINUTES = 30
MIN_PASSWORD_LENGTH = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


# ---------------------------------------------------------------- bootstrap

def bootstrap(db: Session | None = None) -> dict:
    """Create the first operator from the environment, once."""
    owns = db is None
    db = db or SessionLocal()
    try:
        existing = db.query(AdminUser).count()
        if existing:
            # Deliberately not updated from the environment. See the module docstring.
            return {"created": False, "reason": "an operator account already exists"}

        username, password_hash = _env("ADMIN_USERNAME"), _env("ADMIN_PASSWORD_HASH")
        if not (username and password_hash):
            return {"created": False, "reason": "ADMIN_USERNAME / ADMIN_PASSWORD_HASH not set"}

        db.add(AdminUser(
            username=username, password_hash=password_hash,
            session_epoch=1, created_at=_now(), updated_at=_now(),
        ))
        db.commit()
        print(f"[auth] bootstrapped operator account '{username}' from the environment")
        return {"created": True, "username": username}
    finally:
        if owns:
            db.close()


# ---------------------------------------------------------------- lookup

def get_by_username(db: Session, username: str) -> AdminUser | None:
    return db.query(AdminUser).filter(AdminUser.username == username).first()


def get_sole_admin(db: Session) -> AdminUser | None:
    """The single operator. This app has exactly one by design."""
    return db.query(AdminUser).order_by(AdminUser.id).first()


def has_admin(db: Session) -> bool:
    return db.query(AdminUser).count() > 0


# ---------------------------------------------------------------- changes

def set_password(db: Session, user: AdminUser, new_hash: str) -> None:
    """Change the password and sign out every existing session."""
    user.password_hash = new_hash
    user.session_epoch = (user.session_epoch or 1) + 1
    user.reset_token_hash = None      # any outstanding reset link is now void
    user.reset_expires_at = None
    user.updated_at = _now()
    db.commit()


def set_username(db: Session, user: AdminUser, new_username: str) -> None:
    user.username = new_username
    user.session_epoch = (user.session_epoch or 1) + 1
    user.updated_at = _now()
    db.commit()


# ---------------------------------------------------------------- reset tokens

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_reset_token(db: Session, user: AdminUser) -> str:
    """Mint a single-use reset token. Only its hash is stored.

    Issuing a new token invalidates any previous one, so a link that leaked
    earlier stops working the moment a fresh reset is requested.
    """
    token = secrets.token_urlsafe(32)
    user.reset_token_hash = _hash_token(token)
    user.reset_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=RESET_TTL_MINUTES)).isoformat()
    user.updated_at = _now()
    db.commit()
    return token


def consume_reset_token(db: Session, token: str) -> AdminUser | None:
    """Return the user this token resets, and void the token. None if invalid.

    Compared in constant time against the stored hash, and cleared whether or not
    the reset then succeeds — a token is single-use even on a failed attempt.
    """
    if not token:
        return None
    candidate = _hash_token(token)
    for user in db.query(AdminUser).filter(AdminUser.reset_token_hash.isnot(None)).all():
        if not secrets.compare_digest(user.reset_token_hash or "", candidate):
            continue
        expires = user.reset_expires_at
        user.reset_token_hash = None
        user.reset_expires_at = None
        db.commit()
        if not expires or datetime.fromisoformat(expires) < datetime.now(timezone.utc):
            return None
        return user
    return None
