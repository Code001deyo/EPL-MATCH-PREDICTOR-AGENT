"""Outbound email, via Resend's HTTP API.

Only one message is ever sent: the password-reset link. It goes to a FIXED address
from RESET_EMAIL_TO, never to an address supplied in a request — an endpoint that
mailed a valid reset link wherever the caller asked would hand out account access
to anyone who could type.

If Resend is not configured this does NOT pretend to have sent anything. It
returns False and logs loudly, so a misconfiguration is visible to the operator
instead of looking like a delivery problem for weeks.
"""
from __future__ import annotations

import os

import httpx

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def is_configured() -> bool:
    return bool(_env("RESEND_API_KEY") and _env("RESET_EMAIL_TO"))


def send_reset_email(reset_url: str, username: str) -> bool:
    """Send the reset link. True only if Resend accepted it."""
    api_key = _env("RESEND_API_KEY")
    to = _env("RESET_EMAIL_TO")
    sender = _env("RESET_EMAIL_FROM", "EPL Predictor <noreply@hanovatechnologies.co.ke>")

    if not api_key or not to:
        print(
            "[mail] CANNOT SEND PASSWORD RESET: "
            f"RESEND_API_KEY={'set' if api_key else 'MISSING'}, "
            f"RESET_EMAIL_TO={'set' if to else 'MISSING'}. "
            "The caller was given the usual generic response, so this is invisible "
            "to them — fix the configuration or resets cannot be completed."
        )
        return False

    text = (
        f"A password reset was requested for the EPL Predictor operator account "
        f"'{username}'.\n\n"
        f"Open this link to choose a new password. It can be used once and expires "
        f"in 30 minutes:\n\n{reset_url}\n\n"
        f"If you did not request this, no action is needed — the link cannot be used "
        f"without opening it, and requesting a new reset invalidates this one."
    )

    try:
        response = httpx.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": sender,
                "to": [to],
                "subject": "EPL Predictor — password reset",
                "text": text,
            },
            timeout=15,
        )
        if response.status_code >= 400:
            # The body carries Resend's reason — an unverified domain, usually.
            print(f"[mail] Resend rejected the reset email: HTTP {response.status_code} {response.text[:300]}")
            return False
        return True
    except Exception as exc:
        print(f"[mail] could not reach Resend: {type(exc).__name__}: {exc}")
        return False
