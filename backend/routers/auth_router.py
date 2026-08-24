"""Login, logout, and "who am I".

Deliberately small. There is no registration, no password reset and no account
management: the operator is configured through environment variables, so a
self-service reset flow would be a larger hole than the one it closes.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

import auth
from ratelimit import limit

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginRequest, request: Request, response: Response):
    # The tightest limit in the app. There is one account and one password, so
    # this endpoint is the entire attack surface for guessing it.
    limit(request, "auth-login", capacity=5, per_seconds=300)

    if not auth.is_configured():
        raise HTTPException(status_code=503, detail="Admin auth is not configured on this server.")

    expected_user = (auth._env("ADMIN_USERNAME") or "")
    # Both checks always run and the failure is a single message: a response that
    # distinguished "no such user" from "wrong password" would confirm the
    # username, and the timing of an early return would too.
    user_ok = secrets.compare_digest(body.username, expected_user)
    pass_ok = auth.verify_password(body.password, auth._env("ADMIN_PASSWORD_HASH"))
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    auth.set_session_cookie(response, auth.issue_session(expected_user))
    return {"username": expected_user, "admin": True}


@router.post("/auth/logout")
def logout(response: Response):
    auth.clear_session_cookie(response)
    return {"admin": False}


@router.get("/auth/me")
def me(request: Request):
    """Who the caller is. Public — it answers "nobody" rather than 401.

    The frontend calls this on every page load to decide whether to show the admin
    link, so a 401 here would be an error in the console on every anonymous visit.
    """
    return {
        "admin": auth.current_admin(request) is not None if auth.is_configured() else False,
        "username": auth.current_admin(request) if auth.is_configured() else None,
        # Lets the UI say "admin is not configured on this server" instead of
        # showing a login form that cannot possibly succeed.
        "configured": auth.is_configured(),
    }
