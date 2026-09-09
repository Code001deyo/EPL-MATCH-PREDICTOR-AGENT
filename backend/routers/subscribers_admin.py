"""Managing subscribers, for the operator.

A separate router from `subscribe.py` for two reasons. That file is the public
surface and is already at the length this project splits at; and everything here
is admin-only, so keeping the two apart makes it obvious at a glance which
endpoints a stranger can reach.

**These endpoints return email addresses.** That is the point of them - an
operator who cannot see who is on the list cannot manage it - but it makes them
the only place in this codebase where personal data leaves the database, so every
one carries `require_admin`. The public `/subscribe/status` still returns a count
and nothing else.

The privacy policy says an address will be erased on request. `DELETE` here is
what makes that promise something a person can actually carry out, rather than a
sentence on a page.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import require_admin
from db.database import SessionLocal
from db.subscribers import NotificationLog, Subscriber

router = APIRouter(prefix="/admin/subscribers", tags=["admin"],
                   dependencies=[Depends(require_admin)])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _state(row: Subscriber) -> str:
    """One word for where a subscriber is, rather than three timestamps to read."""
    if row.unsubscribed_at:
        return "unsubscribed"
    if row.confirmed_at:
        return "active"
    return "pending"


@router.get("")
def list_subscribers(db: Session = Depends(get_db)):
    """Everyone on the list, with how many emails each has been sent.

    Includes pending and unsubscribed rows, not just active ones. An operator
    looking at "why did this person not get an email" needs to see that the
    address never confirmed, and hiding the row would make that invisible.
    """
    rows = db.query(Subscriber).order_by(Subscriber.created_at.desc()).all()

    # One grouped query rather than a count per subscriber. Twenty subscribers
    # would otherwise be twenty-one round trips on an instance with 0.1 vCPU.
    from sqlalchemy import func

    counts = dict(
        db.query(NotificationLog.subscriber_id, func.count(NotificationLog.id))
        .group_by(NotificationLog.subscriber_id)
        .all()
    )

    subscribers = [
        {
            "id": row.id,
            "email": row.email,
            "state": _state(row),
            "created_at": row.created_at,
            "confirmed_at": row.confirmed_at,
            "unsubscribed_at": row.unsubscribed_at,
            "emails_sent": counts.get(row.id, 0),
        }
        for row in rows
    ]

    return {
        "subscribers": subscribers,
        "total": len(subscribers),
        "active": sum(1 for s in subscribers if s["state"] == "active"),
        "pending": sum(1 for s in subscribers if s["state"] == "pending"),
    }


@router.post("/{subscriber_id}/unsubscribe")
def unsubscribe_subscriber(subscriber_id: int, db: Session = Depends(get_db)):
    """Stop sending to one address, without deleting it.

    The row is kept and marked, which is the same thing the subscriber's own
    unsubscribe link does. Keeping it is deliberate: it is a suppression record,
    so a later import cannot quietly put the address back on the list.
    """
    from datetime import datetime, timezone

    row = db.query(Subscriber).filter(Subscriber.id == subscriber_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No subscriber {subscriber_id}")

    if not row.unsubscribed_at:
        row.unsubscribed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.commit()

    return {"id": row.id, "email": row.email, "state": _state(row)}


@router.post("/{subscriber_id}/resubscribe")
def resubscribe_subscriber(subscriber_id: int, db: Session = Depends(get_db)):
    """Undo an unsubscribe, for the case where it was done by mistake.

    Only clears the unsubscribe. It does **not** confirm the address: an operator
    must not be able to opt somebody in on their behalf, which is the whole point
    of the double opt-in. A row that never confirmed goes back to pending and has
    to click a link like anyone else.
    """
    row = db.query(Subscriber).filter(Subscriber.id == subscriber_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No subscriber {subscriber_id}")

    row.unsubscribed_at = None
    db.commit()
    return {"id": row.id, "email": row.email, "state": _state(row)}


@router.delete("/{subscriber_id}")
def delete_subscriber(subscriber_id: int, db: Session = Depends(get_db)):
    """Erase an address and everything recorded about it.

    The privacy policy offers erasure on request; this is what carries it out.
    The notification log rows go too - they are a record of what was sent to that
    person, so leaving them behind would be keeping the data the erasure was
    asked about.

    Deliberately separate from unsubscribe. Unsubscribing keeps a suppression
    record so the address cannot be silently re-added; erasing removes that
    protection along with everything else, which is the person's choice to make,
    not a tidier default.
    """
    row = db.query(Subscriber).filter(Subscriber.id == subscriber_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No subscriber {subscriber_id}")

    email = row.email
    sent = db.query(NotificationLog).filter(
        NotificationLog.subscriber_id == subscriber_id
    ).delete()
    db.delete(row)
    db.commit()

    return {"deleted": True, "email": email, "notification_rows_removed": sent}
