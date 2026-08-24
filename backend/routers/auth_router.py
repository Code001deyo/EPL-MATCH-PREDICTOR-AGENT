"""Sign in, sign out, and operator account management.

There is exactly one operator account. That shapes several decisions here: no
registration, no user list, and a reset that always mails a fixed address rather
than one the caller supplies.
"""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
import mailer
from db import adminuser
from db.adminuser import MIN_PASSWORD_LENGTH
from db.database import get_db
from ratelimit import limit

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangeUsernameRequest(BaseModel):
    current_password: str
    new_username: str


class ForgotRequest(BaseModel):
    username: str


class ResetRequest(BaseModel):
    token: str
    new_password: str


# The same body regardless of whether the account exists, whether a mail was sent,
# or whether Resend accepted it. Any variation turns /auth/forgot into a way to
# confirm a username, and a reset endpoint that confirms usernames is a reset
# endpoint that helps an attacker.
_FORGOT_RESPONSE = {
    "sent": True,
    "detail": "If that account exists, a reset link has been sent to the address on file.",
}


def _validate_password(password: str) -> None:
    """Length is enforced here, not only in the form.

    A browser check is a convenience for the operator; it is not a control,
    because nothing stops a caller posting straight to the endpoint.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )


@router.post("/auth/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    # The tightest limit in the app: one account, one password, and this endpoint
    # is the whole guessing surface.
    limit(request, "auth-login", capacity=5, per_seconds=300)

    if not auth.is_configured():
        raise HTTPException(status_code=503, detail="Admin auth is not configured on this server.")

    # First login on a fresh database mints the account from the environment.
    adminuser.bootstrap(db)

    user = adminuser.get_by_username(db, body.username)
    # Both checks always run and the failure is one message. Distinguishing
    # "no such user" from "wrong password" confirms the username, and returning
    # early on an unknown user leaks the same thing through response timing.
    password_ok = auth.verify_password(
        body.password,
        user.password_hash if user else "scrypt$00$00",
    )
    if not (user and password_ok):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    auth.set_session_cookie(response, auth.issue_session(user.username, user.session_epoch or 1))
    return {"username": user.username, "admin": True}


@router.post("/auth/logout")
def logout(response: Response):
    auth.clear_session_cookie(response)
    return {"admin": False}


@router.get("/auth/me")
def me(request: Request):
    """Who the caller is. Public — answers "nobody" rather than 401.

    Only the operator route calls this, so it is not on the public site's request
    path; a 401 here would still be wrong, because "signed out" is a normal answer
    to this question rather than an error.
    """
    configured = auth.is_configured()
    who = auth.current_admin(request) if configured else None
    return {"admin": who is not None, "username": who, "configured": configured}


@router.post("/auth/change-password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _who: str = Depends(auth.require_admin),
):
    """Change the password.

    The current password is required even though the caller already holds a valid
    session. A session alone must not be enough to change the credential — someone
    with a borrowed cookie could otherwise lock the real operator out of their own
    account.
    """
    limit(request, "auth-change", capacity=10, per_seconds=300)

    user = adminuser.get_sole_admin(db)
    if not user or not auth.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    _validate_password(body.new_password)

    adminuser.set_password(db, user, auth.hash_password(body.new_password))
    # Every other session is now invalid. Reissue this one so the operator is not
    # signed out by their own successful action.
    auth.set_session_cookie(response, auth.issue_session(user.username, user.session_epoch))
    return {"changed": True, "other_sessions_signed_out": True}


@router.post("/auth/change-username")
def change_username(
    body: ChangeUsernameRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _who: str = Depends(auth.require_admin),
):
    limit(request, "auth-change", capacity=10, per_seconds=300)

    user = adminuser.get_sole_admin(db)
    if not user or not auth.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    new_username = body.new_username.strip()
    if len(new_username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")

    adminuser.set_username(db, user, new_username)
    auth.set_session_cookie(response, auth.issue_session(user.username, user.session_epoch))
    return {"changed": True, "username": user.username}


@router.post("/auth/forgot")
def forgot(body: ForgotRequest, request: Request, db: Session = Depends(get_db)):
    """Mail a reset link to the address on file.

    Always answers identically. The work below happens or does not; the caller
    cannot tell which, which is the entire point.
    """
    limit(request, "auth-forgot", capacity=3, per_seconds=900)

    user = adminuser.get_by_username(db, body.username.strip())
    if user is None:
        # Deliberately silent to the caller, and noted server-side so a genuine
        # operator typo is diagnosable from the logs.
        print(f"[auth] reset requested for unknown account '{body.username.strip()[:40]}'")
        return _FORGOT_RESPONSE

    token = adminuser.issue_reset_token(db, user)
    base = (os.environ.get("RESET_LINK_BASE") or "https://novapl.vercel.app").rstrip("/")
    reset_url = f"{base}/secure-model?reset={token}"

    if not mailer.send_reset_email(reset_url, user.username):
        # The token stays valid — the failure is delivery, not the reset. Logged
        # with the link so the operator can still recover from the server logs
        # while the mail configuration is fixed.
        print(f"[auth] reset link could not be emailed. Link for manual recovery: {reset_url}")

    return _FORGOT_RESPONSE


@router.post("/auth/reset")
def reset(body: ResetRequest, request: Request, db: Session = Depends(get_db)):
    limit(request, "auth-reset", capacity=10, per_seconds=900)

    _validate_password(body.new_password)
    user = adminuser.consume_reset_token(db, body.token)
    if user is None:
        # One message for expired, already-used, and never-valid. Which of the
        # three it was is not something a caller needs, and telling them turns
        # this into an oracle for guessing tokens.
        raise HTTPException(status_code=400, detail="That reset link is invalid or has expired.")

    adminuser.set_password(db, user, auth.hash_password(body.new_password))
    return {"reset": True, "username": user.username}
