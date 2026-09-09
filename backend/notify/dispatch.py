"""Send the notifications that are due, exactly once each.

`queue.py` decides *what* is due; this sends it and records that it went.

Sending exactly once is not enforced by checking first. It is enforced by the
unique index on (fixture, subscriber, kind) in db/subscribers.py: the log row is
written *before* the message is handed to Resend, and rolled back if the send
fails. Of the two failure modes, a logged email that never arrived is a missed
alert; an email delivered twice is how a small sending domain gets blocked.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from db.subscribers import (
    KIND_POST,
    KIND_PRE,
    active_subscribers,
    already_sent,
    record_sent,
)
from notify import templates
from notify.queue import due_post_match, due_pre_match


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unsubscribe_url(token: str) -> str:
    base = (os.environ.get("PUBLIC_SITE_URL") or "").rstrip("/")
    return f"{base}/api/subscribe/unsubscribe?token={token}"


def _send_to_all(db, fixture, kind, build_message) -> dict:
    """Send one fixture's message to every subscriber not already sent it."""
    from mailer import send

    subscribers = active_subscribers(db)
    if not subscribers:
        return {"sent": 0, "failed": 0, "skipped": 0}

    seen = already_sent(db, fixture.pl_fixture_id, kind)
    sent = failed = skipped = 0

    for subscriber in subscribers:
        if subscriber.id in seen:
            skipped += 1
            continue

        # Claim the send before making it. If a concurrent run claimed it first
        # this returns False and we do not send — that is the duplicate being
        # prevented at the database rather than by a check that can race.
        if not record_sent(db, fixture.pl_fixture_id, subscriber.id, kind):
            skipped += 1
            continue

        subject, body = build_message(_unsubscribe_url(subscriber.unsubscribe_token))
        ok = send(
            subscriber.email, subject, body,
            headers={"List-Unsubscribe": f"<{_unsubscribe_url(subscriber.unsubscribe_token)}>"},
        )
        if ok:
            sent += 1
        else:
            # Undo the claim so a later run can retry. A logged send that never
            # left is the one failure this design must not make permanent.
            failed += 1
            from db.subscribers import NotificationLog
            db.query(NotificationLog).filter(
                NotificationLog.pl_fixture_id == fixture.pl_fixture_id,
                NotificationLog.subscriber_id == subscriber.id,
                NotificationLog.kind == kind,
            ).delete()
            db.commit()

    return {"sent": sent, "failed": failed, "skipped": skipped}


def dispatch(db, now: datetime | None = None) -> dict:
    """Send everything currently due. Returns what happened, per kind."""
    from models.fixture_prediction import predict_now, store_prediction, stored_prediction

    now = now or _now()
    report = {
        "at": now.isoformat(timespec="seconds"),
        "pre": {"fixtures": 0, "sent": 0, "failed": 0, "skipped": 0},
        "post": {"fixtures": 0, "sent": 0, "failed": 0, "skipped": 0},
        "errors": [],
    }

    if not active_subscribers(db):
        # Nothing to do, and worth saying so explicitly: "0 sent" with no
        # subscribers is a different situation from "0 sent" with a broken mailer.
        report["note"] = "no confirmed subscribers"
        return report

    # --- before kickoff ---
    for fixture in due_pre_match(db, now):
        try:
            record = stored_prediction(db, fixture.season, fixture.home_team, fixture.away_team)
            if record is None:
                # Nobody clicked Predict on this match. Make the prediction now,
                # rather than mailing about a fixture with nothing to say — and
                # store it, so the site and the email agree and the call can be
                # scored afterwards.
                result = predict_now(db, fixture.home_team, fixture.away_team,
                                     (fixture.kickoff_utc or "")[:10])
                record = store_prediction(
                    db, home_team=fixture.home_team, away_team=fixture.away_team,
                    season=fixture.season, matchweek=fixture.matchweek, result=result,
                )

            pred = {
                "predicted_home": record.predicted_home,
                "predicted_away": record.predicted_away,
                "home_win_prob": record.home_win_prob,
                "draw_prob": record.draw_prob,
                "away_win_prob": record.away_win_prob,
            }
            counts = _send_to_all(
                db, fixture, KIND_PRE,
                lambda url, f=fixture, p=pred: templates.pre_match(f, p, url),
            )
            report["pre"]["fixtures"] += 1
            for k in ("sent", "failed", "skipped"):
                report["pre"][k] += counts[k]
        except Exception as exc:
            # One unpredictable fixture must not stop the rest of a matchday.
            report["errors"].append(
                f"pre {fixture.home_team} v {fixture.away_team}: {type(exc).__name__}: {exc}"
            )

    # --- after the final whistle ---
    for fixture, home_goals, away_goals in due_post_match(db, now):
        try:
            record = stored_prediction(db, fixture.season, fixture.home_team, fixture.away_team)
            pred = None
            if record is not None:
                pred = {
                    "predicted_home": record.predicted_home,
                    "predicted_away": record.predicted_away,
                    "home_win_prob": record.home_win_prob,
                    "draw_prob": record.draw_prob,
                    "away_win_prob": record.away_win_prob,
                }
            counts = _send_to_all(
                db, fixture, KIND_POST,
                lambda url, f=fixture, p=pred, h=home_goals, a=away_goals:
                    templates.post_match(f, p, h, a, url),
            )
            report["post"]["fixtures"] += 1
            for k in ("sent", "failed", "skipped"):
                report["post"][k] += counts[k]
        except Exception as exc:
            report["errors"].append(
                f"post {fixture.home_team} v {fixture.away_team}: {type(exc).__name__}: {exc}"
            )

    return report
