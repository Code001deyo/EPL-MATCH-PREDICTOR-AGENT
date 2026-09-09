"""The two promises the notification system makes.

**Nobody is mailed who did not ask.** A row exists the moment an address is typed,
but nothing is sent until the address itself opens a confirmation link. Without
this, anyone could subscribe anyone.

**Nobody is mailed twice.** The dispatcher runs from a five-minute cron. Cron
fires late, overlaps and retries, so "already sent?" cannot be a check followed by
a send — two overlapping runs would both pass the check. The guarantee has to come
from the unique index.

These tests run against an isolated SQLite database and a fake mailer. Nothing
here sends real email.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import Base  # noqa: E402
from db import subscribers as subs  # noqa: E402
from db.fixtures import Fixture  # noqa: E402
from notify import queue  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/notify.db",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _fixture(db, minutes_from_now, status="U", pl_id=1001):
    kickoff = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    row = Fixture(
        pl_fixture_id=pl_id, season="2026-27", matchweek=4,
        home_team="Arsenal", away_team="Chelsea",
        kickoff_utc=kickoff.isoformat(), kickoff_label="Sat, 15:00", status=status,
    )
    db.add(row)
    db.commit()
    return row


# --- double opt-in --------------------------------------------------------

def test_a_new_address_is_not_mailable_until_it_confirms(db):
    subs.subscribe(db, "someone@example.com")
    assert subs.active_subscribers(db) == [], (
        "an unconfirmed address must never be sent to — otherwise anyone can "
        "subscribe anyone by typing their address"
    )


def test_confirming_makes_it_mailable_and_burns_the_token(db):
    row, needs = subs.subscribe(db, "someone@example.com")
    assert needs
    token = row.confirm_token

    assert subs.confirm(db, token) is not None
    assert len(subs.active_subscribers(db)) == 1
    # Single use: a leaked link in an old inbox cannot be replayed.
    assert subs.confirm(db, token) is None


def test_email_is_case_folded_so_one_person_is_one_row(db):
    subs.subscribe(db, "Harry@Example.com")
    subs.subscribe(db, "harry@example.com")
    from db.subscribers import Subscriber
    assert db.query(Subscriber).count() == 1, "one address must not become two rows and two emails"


def test_resubscribing_an_active_address_does_not_reset_it(db):
    row, _ = subs.subscribe(db, "someone@example.com")
    subs.confirm(db, row.confirm_token)

    _, needs = subs.subscribe(db, "someone@example.com")
    assert not needs, (
        "re-submitting an active address must not un-confirm it, or anyone could "
        "silently unsubscribe a stranger by submitting their address"
    )
    assert len(subs.active_subscribers(db)) == 1


def test_unsubscribe_works_without_a_login_and_is_idempotent(db):
    row, _ = subs.subscribe(db, "someone@example.com")
    subs.confirm(db, row.confirm_token)

    assert subs.unsubscribe(db, row.unsubscribe_token) is not None
    assert subs.active_subscribers(db) == []
    # A second click must not error: mail clients pre-fetch links.
    assert subs.unsubscribe(db, row.unsubscribe_token) is not None


# --- send exactly once ----------------------------------------------------

def test_the_same_notification_cannot_be_logged_twice(db):
    row, _ = subs.subscribe(db, "someone@example.com")
    subs.confirm(db, row.confirm_token)

    assert subs.record_sent(db, 1001, row.id, subs.KIND_PRE) is True
    # This is the overlapping-cron case. The second claim must be refused by the
    # unique index, not by a check that two concurrent runs could both pass.
    assert subs.record_sent(db, 1001, row.id, subs.KIND_PRE) is False


def test_pre_and_post_are_separate_sends(db):
    row, _ = subs.subscribe(db, "someone@example.com")
    subs.confirm(db, row.confirm_token)
    assert subs.record_sent(db, 1001, row.id, subs.KIND_PRE) is True
    assert subs.record_sent(db, 1001, row.id, subs.KIND_POST) is True, (
        "the result email is a different message from the prediction email"
    )


# --- the due queue --------------------------------------------------------

def test_a_fixture_kicking_off_soon_is_due(db):
    _fixture(db, minutes_from_now=8)
    assert len(queue.due_pre_match(db)) == 1


def test_a_fixture_that_has_already_kicked_off_is_not_due(db):
    _fixture(db, minutes_from_now=-5)
    assert queue.due_pre_match(db) == [], (
        "a 'before the match' email delivered after kickoff is worse than none"
    )


def test_a_fixture_far_in_the_future_is_not_due(db):
    _fixture(db, minutes_from_now=60 * 24)
    assert queue.due_pre_match(db) == []


def test_a_fixture_with_no_published_kickoff_is_never_due(db):
    row = _fixture(db, minutes_from_now=8)
    row.kickoff_utc = None
    db.commit()
    assert queue.due_pre_match(db) == [], (
        "the league publishes fixtures before fixing their times; a guessed time "
        "would mail people at the wrong moment"
    )


def test_post_match_waits_for_the_result_not_just_the_clock(db):
    # Kicked off well over three hours ago, so the clock says it is finished —
    # but no row in match_results, so the score is not known yet.
    _fixture(db, minutes_from_now=-200)
    assert queue.due_post_match(db) == [], (
        "mailing 'the match has finished' with no score in hand is worse than waiting"
    )


def test_post_match_is_due_once_the_result_lands(db):
    from db.database import MatchResult

    _fixture(db, minutes_from_now=-200)
    db.add(MatchResult(season="2026-27", matchweek=4, date="2026-09-12",
                       home_team="Arsenal", away_team="Chelsea",
                       home_goals=2, away_goals=1, division="E0"))
    db.commit()

    due = queue.due_post_match(db)
    assert len(due) == 1
    _, home_goals, away_goals = due[0]
    assert (home_goals, away_goals) == (2, 1)


# --- what the emails say --------------------------------------------------

def test_the_post_match_email_reports_a_wrong_call_as_a_wrong_call(db):
    from notify import templates

    fixture = _fixture(db, minutes_from_now=-200)
    pred = {"predicted_home": 2, "predicted_away": 0, "home_win_prob": 0.6,
            "draw_prob": 0.2, "away_win_prob": 0.2}
    _, body = templates.post_match(fixture, pred, 0, 3, "https://x/u")
    assert "Called it wrong." in body, (
        "hiding the misses makes the running record meaningless"
    )


def test_the_post_match_email_does_not_invent_a_prediction_after_the_fact(db):
    from notify import templates

    fixture = _fixture(db, minutes_from_now=-200)
    _, body = templates.post_match(fixture, None, 1, 1, "https://x/u")
    assert "No prediction was recorded" in body


def test_every_email_carries_a_way_out(db):
    from notify import templates

    fixture = _fixture(db, minutes_from_now=10)
    pred = {"predicted_home": 2, "predicted_away": 1, "home_win_prob": 0.5,
            "draw_prob": 0.25, "away_win_prob": 0.25}
    _, pre_body = templates.pre_match(fixture, pred, "https://x/unsub?token=abc")
    _, post_body = templates.post_match(fixture, pred, 2, 1, "https://x/unsub?token=abc")
    assert "https://x/unsub?token=abc" in pre_body
    assert "https://x/unsub?token=abc" in post_body


# --- the whole path, with a stub mailer -----------------------------------

def _confirmed(db, email="fan@example.com"):
    row, _ = subs.subscribe(db, email)
    subs.confirm(db, row.confirm_token)
    return row


def _stored_prediction(db, season="2026-27"):
    """A prediction already in the table, so dispatch does not run the model."""
    from db.database import Prediction
    db.add(Prediction(
        fixture="Arsenal vs Chelsea", season=season, matchweek=4,
        predicted_home=2, predicted_away=1,
        home_win_prob=0.55, draw_prob=0.24, away_win_prob=0.21,
        confidence=0.7, created_at="2026-09-01T00:00:00", times_predicted=1,
    ))
    db.commit()


def test_a_due_fixture_is_sent_once_and_only_once(db, monkeypatch):
    """The overlapping-cron case, end to end.

    Two dispatches run back to back, exactly as a late cron tick would. The first
    sends; the second must send nothing at all.
    """
    import mailer
    from notify.dispatch import dispatch as run_dispatch

    outbox = []
    monkeypatch.setattr(mailer, "send",
                        lambda to, subject, text, **kw: outbox.append((to, subject)) or True)

    _confirmed(db)
    _fixture(db, minutes_from_now=8)
    _stored_prediction(db)

    first = run_dispatch(db)
    assert first["pre"]["sent"] == 1, first
    assert len(outbox) == 1
    assert "Arsenal v Chelsea" in outbox[0][1]

    second = run_dispatch(db)
    assert second["pre"]["sent"] == 0, "a second tick must not re-send"
    assert len(outbox) == 1, "the subscriber must receive exactly one email"


def test_a_failed_send_is_retried_rather_than_recorded_as_delivered(db, monkeypatch):
    """A logged email that never left is the one failure this must not make permanent."""
    import mailer
    from notify.dispatch import dispatch as run_dispatch

    _confirmed(db)
    _fixture(db, minutes_from_now=8)
    _stored_prediction(db)

    monkeypatch.setattr(mailer, "send", lambda *a, **kw: False)
    failed = run_dispatch(db)
    assert failed["pre"]["failed"] == 1
    assert failed["pre"]["sent"] == 0

    # Mailer recovers. The next tick must actually deliver, not skip it as sent.
    outbox = []
    monkeypatch.setattr(mailer, "send",
                        lambda to, subject, text, **kw: outbox.append(to) or True)
    recovered = run_dispatch(db)
    assert recovered["pre"]["sent"] == 1, "a failed send must be retried on the next tick"
    assert outbox == ["fan@example.com"]


def test_nothing_is_sent_when_nobody_has_confirmed(db, monkeypatch):
    import mailer
    from notify.dispatch import dispatch as run_dispatch

    sent = []
    monkeypatch.setattr(mailer, "send", lambda *a, **kw: sent.append(a) or True)

    subs.subscribe(db, "unconfirmed@example.com")   # typed, never confirmed
    _fixture(db, minutes_from_now=8)
    _stored_prediction(db)

    report = run_dispatch(db)
    assert sent == [], "an unconfirmed address must never receive mail"
    assert report.get("note") == "no confirmed subscribers"
