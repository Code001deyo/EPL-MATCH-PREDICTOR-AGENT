"""Subscribers, and the log that stops a notification being sent twice.

The site had no subscriber concept at all. `mailer.py` sends exactly one message
— a password-reset link, to a single fixed address from `RESET_EMAIL_TO` — and
that restriction is deliberate: an endpoint that mails a reset link wherever the
caller asks hands out account access to anyone who can type. Nothing here relaxes
that. Subscriber mail is a separate path with its own rules, and the reset path
is left exactly as it was.

Two rules this schema enforces rather than hopes for:

**Double opt-in.** A row exists from the moment someone types an address, but
`confirmed_at` stays NULL until they click the link mailed to it. Only confirmed
rows are ever sent to. Without this, anyone could subscribe anyone, and the
address would never have proved it wanted the mail.

**Send exactly once.** `notification_log` has a unique index on
(fixture, subscriber, kind). The dispatcher runs from a five-minute cron; cron
fires late, overlaps, and retries. The index is what makes a second attempt a
no-op at the database rather than a duplicate email — the check-then-send pattern
alone would race two overlapping runs against each other.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Text, UniqueConstraint, Index

from db.database import Base

# The two things a subscriber is sent about one fixture.
KIND_PRE = "pre"     # before kickoff: the prediction
KIND_POST = "post"   # after the final whistle: result, and how the call went
KINDS = (KIND_PRE, KIND_POST)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_token() -> str:
    """A confirm/unsubscribe token.

    `secrets`, not `random`: these are the only credential a click carries. 32
    bytes so guessing one is not a realistic way to confirm somebody else's
    address or unsubscribe them.
    """
    return secrets.token_urlsafe(32)


class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, index=True)

    # Stored lowercased and unique. Case-folding at write time means
    # Harry@x.com and harry@x.com cannot become two rows and two copies of every
    # email.
    email = Column(Text, unique=True, index=True, nullable=False)

    confirm_token = Column(Text, index=True, nullable=True)
    confirmed_at = Column(Text, nullable=True)

    # Never expires and never requires a login. An unsubscribe link that can stop
    # working is a subscriber who cannot leave, which is both rude and, for bulk
    # mail, the fastest route to a spam complaint.
    unsubscribe_token = Column(Text, index=True, nullable=False)

    created_at = Column(Text)
    unsubscribed_at = Column(Text, nullable=True)


class NotificationLog(Base):
    """One row per (fixture, subscriber, kind) actually sent."""

    __tablename__ = "notification_log"
    __table_args__ = (
        # The whole safety property of the dispatcher is this constraint.
        UniqueConstraint("pl_fixture_id", "subscriber_id", "kind",
                         name="uq_notification_once"),
    )

    id = Column(Integer, primary_key=True, index=True)
    pl_fixture_id = Column(Integer, index=True, nullable=False)
    subscriber_id = Column(Integer, index=True, nullable=False)
    kind = Column(Text, nullable=False)
    sent_at = Column(Text)


# "What has already gone out for this fixture" is the dispatcher's hot query.
Index("idx_notification_fixture_kind", NotificationLog.pl_fixture_id, NotificationLog.kind)


# --- operations ----------------------------------------------------------

def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def subscribe(db, email: str) -> tuple[Subscriber, bool]:
    """Create or re-open a subscription. Returns (subscriber, needs_confirmation).

    Deliberately idempotent. Re-subscribing an address that is already confirmed
    does NOT reset it to unconfirmed and does not mail anything — otherwise
    anyone could silently unsubscribe a stranger by submitting their address and
    never clicking the link.
    """
    email = normalise_email(email)
    row = db.query(Subscriber).filter(Subscriber.email == email).one_or_none()

    if row is None:
        row = Subscriber(
            email=email,
            confirm_token=new_token(),
            unsubscribe_token=new_token(),
            created_at=_now(),
        )
        db.add(row)
        db.commit()
        return row, True

    if row.confirmed_at and not row.unsubscribed_at:
        return row, False          # already active; nothing to do, nothing to send

    # Previously unsubscribed, or never confirmed. Re-open with a fresh token so
    # an old link in an old inbox cannot be replayed.
    row.confirm_token = new_token()
    row.unsubscribed_at = None
    row.confirmed_at = None
    db.commit()
    return row, True


def confirm(db, token: str) -> Subscriber | None:
    """Complete a double opt-in. Single-use: the token is cleared on success."""
    if not token:
        return None
    row = db.query(Subscriber).filter(Subscriber.confirm_token == token).one_or_none()
    if row is None:
        return None
    row.confirmed_at = _now()
    row.confirm_token = None
    row.unsubscribed_at = None
    db.commit()
    return row


def unsubscribe(db, token: str) -> Subscriber | None:
    """Stop sending. The token survives, so a second click is harmless."""
    if not token:
        return None
    row = db.query(Subscriber).filter(Subscriber.unsubscribe_token == token).one_or_none()
    if row is None:
        return None
    if not row.unsubscribed_at:
        row.unsubscribed_at = _now()
        db.commit()
    return row


def active_subscribers(db) -> list[Subscriber]:
    """Confirmed and not unsubscribed — the only people who may be mailed."""
    return (
        db.query(Subscriber)
        .filter(Subscriber.confirmed_at.isnot(None), Subscriber.unsubscribed_at.is_(None))
        .all()
    )


def already_sent(db, pl_fixture_id: int, kind: str) -> set[int]:
    """Subscriber ids already sent this fixture/kind."""
    rows = db.query(NotificationLog.subscriber_id).filter(
        NotificationLog.pl_fixture_id == pl_fixture_id,
        NotificationLog.kind == kind,
    ).all()
    return {r[0] for r in rows}


def record_sent(db, pl_fixture_id: int, subscriber_id: int, kind: str) -> bool:
    """Log a send. False if it was already logged.

    Written *before* the message is handed to the provider, and rolled back if
    the send fails. Of the two failure modes — a logged email that never arrived,
    and an email delivered twice — the first is a missed alert and the second is
    the thing that gets a sending domain blocked.
    """
    db.add(NotificationLog(
        pl_fixture_id=pl_fixture_id,
        subscriber_id=subscriber_id,
        kind=kind,
        sent_at=_now(),
    ))
    try:
        db.commit()
        return True
    except Exception:
        # The unique index rejected it: another run got there first.
        db.rollback()
        return False
