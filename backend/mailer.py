"""Outbound email, via Resend's HTTP API.

Two kinds of message, kept deliberately separate.

**The password-reset link** goes to a FIXED address from RESET_EMAIL_TO, never to
an address supplied in a request - an endpoint that mailed a valid reset link
wherever the caller asked would hand out account access to anyone who could type.
That restriction is unchanged and must stay.

**Match notifications** go to confirmed subscribers, which is a different trust
model and so a different path: the address has proved it wants the mail by
clicking a confirmation link (see db/subscribers.py), the content carries no
credential, and every message carries a working unsubscribe. Subscriber mail must
never reuse the reset path, and the reset path must never accept a caller's
address.

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
            "to them - fix the configuration or resets cannot be completed."
        )
        return False

    text = (
        f"A password reset was requested for the EPL Predictor operator account "
        f"'{username}'.\n\n"
        f"Open this link to choose a new password. It can be used once and expires "
        f"in 30 minutes:\n\n{reset_url}\n\n"
        f"If you did not request this, no action is needed - the link cannot be used "
        f"without opening it, and requesting a new reset invalidates this one."
    )

    return send(to, "EPL Predictor - password reset", text, sender=sender)


class SendResult:
    """What happened to one message.

    Truthy when Resend accepted it, so every existing `if send(...)` caller keeps
    working unchanged. What it adds is the *reason* for a rejection.

    That reason used to exist only as a `print` into a container log, on a free
    instance that sleeps and rotates its logs. From outside the process, "nobody
    subscribed", "the API key is wrong" and "the sending domain is not verified"
    were indistinguishable - all three were a silent False. A mail path that
    cannot say why it failed cannot be configured, only guessed at.
    """

    __slots__ = ("ok", "status", "error", "provider_id")

    def __init__(self, ok: bool, status: int | None = None,
                 error: str | None = None, provider_id: str | None = None):
        self.ok = ok
        self.status = status
        self.error = error
        self.provider_id = provider_id

    def __bool__(self) -> bool:
        return self.ok

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "error": self.error,
            "provider_id": self.provider_id,
        }

    def __repr__(self) -> str:
        return f"SendResult(ok={self.ok}, status={self.status}, error={self.error!r})"


def send(to: str, subject: str, text: str, html: str | None = None,
         sender: str | None = None, headers: dict | None = None) -> SendResult:
    """Hand one message to Resend.

    The single place an email leaves this process. Returns a falsy result and
    logs the reason rather than raising: a caller sending to a list must be able
    to record that one address failed and carry on, and must never be able to
    mistake a rejection for a delivery.
    """
    api_key = _env("RESEND_API_KEY")
    sender = sender or _env("NOTIFY_EMAIL_FROM") or _env(
        "RESET_EMAIL_FROM", "EPL Predictor <noreply@hanovatechnologies.co.ke>")

    if not api_key:
        print("[mail] CANNOT SEND: RESEND_API_KEY is missing. "
              f"Message to {to} ({subject!r}) was NOT delivered.")
        return SendResult(False, error="RESEND_API_KEY is not set on this instance")

    payload = {"from": sender, "to": [to], "subject": subject, "text": text}
    if html:
        payload["html"] = html
    if headers:
        # List-Unsubscribe lives here. Mail clients surface it as a one-click
        # unsubscribe, which is what keeps a small sending domain out of spam
        # folders - a subscriber who cannot leave easily reports instead.
        payload["headers"] = headers

    try:
        response = httpx.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=15,
        )
        if response.status_code >= 400:
            # The body carries Resend's reason - an unverified domain, usually.
            detail = response.text[:300]
            print(f"[mail] Resend rejected {subject!r} to {to}: "
                  f"HTTP {response.status_code} {detail}")
            return SendResult(False, status=response.status_code, error=detail)

        provider_id = None
        try:
            provider_id = (response.json() or {}).get("id")
        except ValueError:
            pass
        return SendResult(True, status=response.status_code, provider_id=provider_id)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        print(f"[mail] could not reach Resend: {reason}")
        return SendResult(False, error=reason)


def notifications_configured() -> bool:
    """Subscriber mail needs a key and a from-address; it has no fixed recipient."""
    return bool(_env("RESEND_API_KEY"))


def send_admin(subject: str, text: str) -> SendResult:
    """Mail the operator.

    Goes to a FIXED address from ADMIN_EMAIL, falling back to RESET_EMAIL_TO, and
    never to an address supplied in a request. That is the same restriction the
    password-reset path has and for the same reason: an operator channel that a
    caller can redirect is not an operator channel.
    """
    to = _env("ADMIN_EMAIL") or _env("RESET_EMAIL_TO")
    if not to:
        print(f"[mail] no ADMIN_EMAIL or RESET_EMAIL_TO set; operator notice "
              f"not sent: {subject!r}")
        return SendResult(False, error="neither ADMIN_EMAIL nor RESET_EMAIL_TO is set")
    return send(to, subject, text)


def mail_settings() -> dict:
    """Which mail settings this instance has, by name and presence only.

    Never a value. The question worth answering from outside is "is this
    configured", and answering it with the secret would mean reading a secret to
    find out whether a secret exists.
    """
    return {
        "RESEND_API_KEY": bool(_env("RESEND_API_KEY")),
        "ADMIN_EMAIL": bool(_env("ADMIN_EMAIL")),
        "RESET_EMAIL_TO": bool(_env("RESET_EMAIL_TO")),
        "NOTIFY_EMAIL_FROM": bool(_env("NOTIFY_EMAIL_FROM")),
        # Not a mail setting as such, but every unsubscribe and privacy link in
        # every message is built on it. Unset means those links have no host,
        # which is a broken link in bulk mail.
        "PUBLIC_SITE_URL": bool(_env("PUBLIC_SITE_URL")),
    }


def sender_address() -> str:
    """The From address messages will actually use.

    Not a secret, and the single most likely cause of a rejection: Resend refuses
    a domain it has not verified, so this is the first thing to look at when mail
    stops leaving.
    """
    return _env("NOTIFY_EMAIL_FROM") or _env(
        "RESET_EMAIL_FROM", "EPL Predictor <noreply@hanovatechnologies.co.ke>")
