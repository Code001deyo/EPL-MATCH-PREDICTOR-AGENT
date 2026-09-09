"""Managing subscribers from the operator console.

These are the only endpoints in the project that return email addresses, so the
first thing asserted is that none of them answer without an admin session. The
public `/subscribe/status` still returns a count and nothing else.

The second thing asserted is the limit on what an operator may do. They can stop
sending to somebody and they can erase them, because both are things the person
would want done on request. They cannot *subscribe* somebody: undoing an
unsubscribe must not confirm an address that never confirmed itself, or the
double opt-in stops being a consent record and becomes a formality an operator
can skip.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import Base  # noqa: E402
from db import subscribers as subs  # noqa: E402
from db.subscribers import NotificationLog, Subscriber  # noqa: E402
from main import app  # noqa: E402
from routers import subscribers_admin  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/admin.db",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    """An admin-authenticated client, with the router bound to the test database."""
    from auth import require_admin

    app.dependency_overrides[subscribers_admin.get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: "test-operator"
    yield TestClient(app)
    app.dependency_overrides.clear()


def _subscriber(db, email, confirmed=True, unsubscribed=False):
    row, _ = subs.subscribe(db, email)
    if confirmed:
        subs.confirm(db, row.confirm_token)
    if unsubscribed:
        subs.unsubscribe(db, row.unsubscribe_token)
    return row


# --- nothing here is public ----------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/admin/subscribers"),
    ("post", "/admin/subscribers/1/unsubscribe"),
    ("post", "/admin/subscribers/1/resubscribe"),
    ("delete", "/admin/subscribers/1"),
])
def test_every_endpoint_refuses_an_anonymous_caller(method, path):
    """These are the only endpoints that return email addresses."""
    unauthenticated = TestClient(app)
    response = getattr(unauthenticated, method)(path)
    assert response.status_code in (401, 503), (
        f"{method.upper()} {path} answered {response.status_code} without an admin session"
    )


# --- the list -------------------------------------------------------------

def test_the_list_shows_state_rather_than_three_timestamps(client, db):
    _subscriber(db, "active@example.com")
    _subscriber(db, "pending@example.com", confirmed=False)
    _subscriber(db, "gone@example.com", unsubscribed=True)

    body = client.get("/admin/subscribers").json()
    states = {s["email"]: s["state"] for s in body["subscribers"]}

    assert states["active@example.com"] == "active"
    assert states["pending@example.com"] == "pending"
    assert states["gone@example.com"] == "unsubscribed"
    assert body["total"] == 3
    assert body["active"] == 1


def test_unconfirmed_addresses_are_listed_not_hidden(client, db):
    """"Why did this person get nothing" is answered by the row being pending.

    Listing only active subscribers would make that invisible and send the
    operator looking for a fault in the mailer.
    """
    _subscriber(db, "never-clicked@example.com", confirmed=False)
    body = client.get("/admin/subscribers").json()
    assert [s["email"] for s in body["subscribers"]] == ["never-clicked@example.com"]
    assert body["pending"] == 1


def test_the_list_reports_how_many_emails_each_has_had(client, db):
    row = _subscriber(db, "reader@example.com")
    subs.record_sent(db, 1001, row.id, subs.KIND_PRE)
    subs.record_sent(db, 1001, row.id, subs.KIND_POST)

    body = client.get("/admin/subscribers").json()
    assert body["subscribers"][0]["emails_sent"] == 2


# --- unsubscribing on someone's behalf ------------------------------------

def test_an_operator_can_stop_sending_to_an_address(client, db):
    row = _subscriber(db, "asked-to-stop@example.com")
    assert len(subs.active_subscribers(db)) == 1

    result = client.post(f"/admin/subscribers/{row.id}/unsubscribe").json()
    assert result["state"] == "unsubscribed"
    assert subs.active_subscribers(db) == []


def test_unsubscribing_twice_is_harmless(client, db):
    row = _subscriber(db, "twice@example.com")
    client.post(f"/admin/subscribers/{row.id}/unsubscribe")
    first = db.query(Subscriber).filter(Subscriber.id == row.id).one().unsubscribed_at

    client.post(f"/admin/subscribers/{row.id}/unsubscribe")
    assert db.query(Subscriber).filter(Subscriber.id == row.id).one().unsubscribed_at == first, (
        "a second unsubscribe must not rewrite the date it happened"
    )


def test_an_operator_cannot_opt_somebody_in(client, db):
    """Resubscribe clears an unsubscribe. It must not confirm an address.

    If it did, an operator could add anyone to the list by typing an address and
    pressing a button, and the double opt-in would stop being a consent record.
    """
    row = _subscriber(db, "never-confirmed@example.com", confirmed=False, unsubscribed=True)

    result = client.post(f"/admin/subscribers/{row.id}/resubscribe").json()
    assert result["state"] == "pending", "an unconfirmed address must not become active"
    assert subs.active_subscribers(db) == []


def test_resubscribe_restores_someone_who_had_confirmed(client, db):
    row = _subscriber(db, "came-back@example.com", unsubscribed=True)
    assert subs.active_subscribers(db) == []

    result = client.post(f"/admin/subscribers/{row.id}/resubscribe").json()
    assert result["state"] == "active"
    assert len(subs.active_subscribers(db)) == 1


# --- erasure --------------------------------------------------------------

def test_deleting_removes_the_record_of_what_was_sent_too(client, db):
    """The policy offers erasure; a half-erasure keeps the data it was asked about."""
    row = _subscriber(db, "erase-me@example.com")
    subs.record_sent(db, 1001, row.id, subs.KIND_PRE)
    subs.record_sent(db, 1002, row.id, subs.KIND_PRE)

    result = client.delete(f"/admin/subscribers/{row.id}").json()
    assert result["deleted"] is True
    assert result["notification_rows_removed"] == 2

    assert db.query(Subscriber).filter(Subscriber.id == row.id).one_or_none() is None
    assert db.query(NotificationLog).filter(
        NotificationLog.subscriber_id == row.id
    ).count() == 0


def test_acting_on_a_subscriber_that_does_not_exist_is_a_404(client, db):
    assert client.post("/admin/subscribers/9999/unsubscribe").status_code == 404
    assert client.delete("/admin/subscribers/9999").status_code == 404
