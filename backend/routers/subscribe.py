"""Subscribe, confirm, unsubscribe, and the dispatch trigger.

Three of these are public and one is not.

`POST /subscribe` answers the **same generic body** whether the address is new,
already confirmed, or invalid. Anything else turns the endpoint into an oracle:
submit an address, read the response, learn whether that person is subscribed.
The same reasoning already governs the password-reset endpoint.

`POST /notifications/dispatch` is admin-only, behind the same `require_admin`
that guards refresh. It is what actually sends mail, so leaving it open would let
anyone empty a rate-limited sending quota - and, on a five-minute cron, do it
repeatedly.
"""

from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import jobs
from auth import require_admin
from db.database import SessionLocal
from db import subscribers as subs
from ratelimit import limit

router = APIRouter(tags=["notifications"])

# Deliberately loose. Strict RFC 5322 validation rejects addresses that work, and
# the real check is the confirmation link: an address that cannot receive mail
# never confirms, so it never gets sent to. This only rejects obvious nonsense
# before it reaches the mailer.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")

# One answer for every outcome. See the module docstring.
GENERIC = {
    "status": "ok",
    "message": (
        "If that address can receive mail, a confirmation link is on its way. "
        "Notifications only start once you open it."
    ),
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _page(title: str, message: str, ok: bool = True) -> HTMLResponse:
    """A plain confirmation page.

    Server-rendered rather than a redirect into the React app: these links are
    opened from an email client, sometimes in a stripped-down browser, and the
    reply has to work without JavaScript or a bundle download.
    """
    colour = "#00ff85" if ok else "#e8003d"
    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - EPL Predictor</title></head>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
             background:#37003c;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#fff">
  <main style="max-width:32rem;padding:2.5rem;text-align:center">
    <div style="width:3rem;height:.25rem;background:{colour};margin:0 auto 1.5rem;border-radius:2px"></div>
    <h1 style="font-size:1.5rem;margin:0 0 .75rem">{title}</h1>
    <p style="margin:0;line-height:1.6;color:#e9d5ff">{message}</p>
  </main>
</body></html>""")


@router.post("/subscribe")
def subscribe(payload: dict, request: Request, db: Session = Depends(get_db)):
    # A public endpoint that sends email is a public endpoint that spends money
    # and sending reputation. Tight, because nobody legitimately subscribes five
    # times a minute.
    limit(request, "subscribe", capacity=5, per_seconds=60)

    email = subs.normalise_email(payload.get("email", ""))
    if not EMAIL_RE.match(email or ""):
        # Still the generic answer. A distinct "that is not an email" reply is
        # harmless on its own but starts the habit of differentiating responses.
        return GENERIC

    row, needs_confirmation = subs.subscribe(db, email)
    if needs_confirmation:
        from mailer import send
        from notify import templates

        # Built from PUBLIC_SITE_URL, never from the request.
        #
        # This used to read the caller's `Origin` header. That is an account
        # takeover waiting to happen: POST /subscribe with somebody else's
        # address and `Origin: https://evil.example`, and this service mails
        # *them* a link to the attacker's site carrying a valid confirm token.
        # A link we send has to be a link we chose.
        #
        # It also fixes the ordinary case. Any client that sends no Origin - curl,
        # a mail client preview, a browser that strips it - produced
        # "/api/subscribe/confirm?token=..." with no host, which is a dead link in
        # the one message that has to work.
        base = (os.environ.get("PUBLIC_SITE_URL") or "").rstrip("/")
        confirm_url = f"{base}/api/subscribe/confirm?token={row.confirm_token}"
        subject, body = templates.confirm_subscription(confirm_url)
        # If this fails, mailer logs loudly. The caller still gets the generic
        # reply - telling them the send failed would reveal the address exists.
        send(email, subject, body)

    return GENERIC


@router.get("/subscribe/confirm")
def confirm(token: str = "", db: Session = Depends(get_db)):
    row = subs.confirm(db, token)
    if row is None:
        return _page(
            "That link has expired",
            "It may already have been used, or replaced by a newer one. "
            "Subscribe again from the site to get a fresh link.",
            ok=False,
        )
    return _page(
        "You're subscribed",
        "You'll get the model's call shortly before each kickoff, and the result "
        "with how that call went shortly after the final whistle. Every email has "
        "an unsubscribe link.",
    )


@router.get("/subscribe/unsubscribe")
def unsubscribe(token: str = "", db: Session = Depends(get_db)):
    row = subs.unsubscribe(db, token)
    if row is None:
        return _page(
            "Link not recognised",
            "This unsubscribe link does not match any subscription. You may "
            "already have been removed.",
            ok=False,
        )
    return _page(
        "Unsubscribed",
        "No further match emails will be sent to this address. "
        "Nothing else is kept about you.",
    )


@router.get("/subscribe/status")
def subscriber_status():
    """Whether sign-ups can be accepted. Nothing about who has signed up.

    This used to return the number of confirmed subscribers, and the sign-up box
    printed it. That is nobody's business but the operator's: on a small list it
    advertises exactly how small, and it is a fact about the service rather than
    anything the person deciding whether to subscribe needs.

    The count still exists, in the operator console behind the admin sign-in.

    What is left is one boolean, and it earns its place: it is the difference
    between "nobody subscribed" and "nothing can be sent", so the UI can close
    the form instead of accepting an address it cannot mail.
    """
    from mailer import notifications_configured

    return {"delivery_configured": notifications_configured()}


@router.post("/notifications/dispatch", status_code=202,
             dependencies=[Depends(require_admin)])
def dispatch_notifications(response: Response):
    """Send whatever is due. Triggered by the five-minute cron.

    A background job for the same reason refresh is: on a matchday this makes a
    prediction for every fixture about to kick off, which outlives the timeout of
    whatever is holding the connection. Jobs are single-flight per kind, so an
    overlapping cron tick joins the running dispatch instead of racing it.
    """
    def work(_job_id):
        from notify import send_due

        db = SessionLocal()
        try:
            return send_due(db)
        finally:
            db.close()

    job, created = jobs.submit("notify", work)
    if not created:
        response.status_code = 200
    return {"job_id": job["id"], "state": job["state"], "started": created, "job": job}


@router.post("/notifications/selftest", dependencies=[Depends(require_admin)])
def notifications_selftest(send: bool = True):
    """Say whether this instance can actually send mail, and why not if it cannot.

    Admin-only, because it spends sending quota - the same reason dispatch is.

    Exists because a rejection used to be a `print` into a container log on a
    free instance that sleeps. From outside, an unverified sending domain, a
    wrong API key and simply having no subscribers all looked the same: nothing
    arrived. This turns that into an answer.

    `send=false` reports the configuration without sending anything, which is the
    safe call to make on a whim.
    """
    from mailer import mail_settings, sender_address, send_admin

    report = {
        "settings": mail_settings(),
        "sender": sender_address(),
        "sent": False,
    }

    # Reported explicitly rather than left to be inferred from a failure: every
    # unsubscribe and privacy link in every message is built on PUBLIC_SITE_URL,
    # so an unset value means broken links in bulk mail rather than a bad send.
    if not report["settings"]["PUBLIC_SITE_URL"]:
        report["warning"] = (
            "PUBLIC_SITE_URL is not set, so unsubscribe and privacy links in "
            "outgoing email have no host and will not resolve."
        )

    if not send:
        return report

    result = send_admin(
        "EPL Predictor - mail self-test",
        """This is a self-test from the EPL Predictor backend.

If you are reading it, the instance can send mail: the API key works and the
sending domain is accepted.

-
EPL Predictor, a product of Hanova Technologies.
""",
    )
    report["sent"] = bool(result)
    report["result"] = result.as_dict()
    return report


@router.get("/notifications/jobs/{job_id}")
def notification_job(job_id: str):
    from fastapi import HTTPException

    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}")
    return job
