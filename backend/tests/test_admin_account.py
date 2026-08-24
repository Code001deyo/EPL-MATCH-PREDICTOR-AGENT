"""Tests for the database-backed operator account.

The behaviour these protect is the whole reason credentials moved out of
environment variables: a password change that does not survive a restart is worse
than no password change at all, because the operator believes it took effect.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import auth
from db import adminuser
from db.database import AdminUser, Base


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "Trojan")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", auth.hash_password("bootstrap-password"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret-not-used-anywhere-real")
    yield


class TestBootstrap:
    def test_creates_the_account_from_the_environment(self, db, env):
        assert adminuser.bootstrap(db)["created"] is True
        assert adminuser.get_by_username(db, "Trojan") is not None

    def test_is_idempotent(self, db, env):
        adminuser.bootstrap(db)
        assert adminuser.bootstrap(db)["created"] is False
        assert db.query(AdminUser).count() == 1

    def test_never_overwrites_a_changed_password(self, db, env):
        """The single most important property here.

        Without it, every restart would silently restore the env-var password and
        a change the operator made would quietly stop being in effect — while the
        old password kept working.
        """
        adminuser.bootstrap(db)
        user = adminuser.get_sole_admin(db)
        adminuser.set_password(db, user, auth.hash_password("the-real-password"))

        adminuser.bootstrap(db)          # simulates the next restart

        user = adminuser.get_sole_admin(db)
        assert auth.verify_password("the-real-password", user.password_hash)
        assert not auth.verify_password("bootstrap-password", user.password_hash)

    def test_never_reverts_a_changed_username(self, db, env):
        adminuser.bootstrap(db)
        adminuser.set_username(db, adminuser.get_sole_admin(db), "Renamed")
        adminuser.bootstrap(db)
        assert adminuser.get_sole_admin(db).username == "Renamed"
        assert adminuser.get_by_username(db, "Trojan") is None

    def test_does_nothing_without_environment_credentials(self, db, monkeypatch):
        monkeypatch.delenv("ADMIN_USERNAME", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
        assert adminuser.bootstrap(db)["created"] is False
        assert db.query(AdminUser).count() == 0


class TestSessionEpoch:
    """A password change must invalidate sessions issued before it. Otherwise a
    stolen cookie survives the reset and the reset achieves nothing against the
    person it was meant to lock out."""

    def test_token_carries_the_epoch(self, env):
        assert auth.read_session(auth.issue_session("Trojan", 7)) == ("Trojan", 7)

    def test_changing_the_password_bumps_the_epoch(self, db, env):
        adminuser.bootstrap(db)
        user = adminuser.get_sole_admin(db)
        before = user.session_epoch
        adminuser.set_password(db, user, auth.hash_password("something-else-long"))
        assert user.session_epoch == before + 1

    def test_changing_the_username_bumps_the_epoch(self, db, env):
        adminuser.bootstrap(db)
        user = adminuser.get_sole_admin(db)
        before = user.session_epoch
        adminuser.set_username(db, user, "NewName")
        assert user.session_epoch == before + 1

    def test_a_token_without_an_epoch_is_rejected(self, env):
        """Tokens minted before epochs existed. Rejected rather than trusted — one
        extra sign-in is the safe direction, an accepted stale session is not."""
        legacy = auth._signer().sign(b"Trojan").decode()
        assert auth.read_session(legacy) is None


class TestResetTokens:
    def _user(self, db, env):
        adminuser.bootstrap(db)
        return adminuser.get_sole_admin(db)

    def test_stored_value_is_not_the_token(self, db, env):
        user = self._user(db, env)
        token = adminuser.issue_reset_token(db, user)
        # Read access to the database must not be enough to complete a reset.
        assert user.reset_token_hash != token
        assert token not in (user.reset_token_hash or "")

    def test_valid_token_resolves_to_the_user(self, db, env):
        user = self._user(db, env)
        token = adminuser.issue_reset_token(db, user)
        assert adminuser.consume_reset_token(db, token).id == user.id

    def test_token_is_single_use(self, db, env):
        user = self._user(db, env)
        token = adminuser.issue_reset_token(db, user)
        adminuser.consume_reset_token(db, token)
        assert adminuser.consume_reset_token(db, token) is None

    def test_expired_token_is_rejected(self, db, env):
        user = self._user(db, env)
        token = adminuser.issue_reset_token(db, user)
        user.reset_expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        db.commit()
        assert adminuser.consume_reset_token(db, token) is None

    def test_issuing_a_new_token_invalidates_the_previous_one(self, db, env):
        """So a link that leaked earlier stops working the moment a fresh reset is
        requested."""
        user = self._user(db, env)
        first = adminuser.issue_reset_token(db, user)
        adminuser.issue_reset_token(db, user)
        assert adminuser.consume_reset_token(db, first) is None

    def test_changing_the_password_voids_an_outstanding_token(self, db, env):
        user = self._user(db, env)
        token = adminuser.issue_reset_token(db, user)
        adminuser.set_password(db, user, auth.hash_password("changed-it-directly"))
        assert adminuser.consume_reset_token(db, token) is None

    @pytest.mark.parametrize("bad", ["", "not-a-token", "x" * 43])
    def test_garbage_is_rejected_without_raising(self, db, env, bad):
        self._user(db, env)
        assert adminuser.consume_reset_token(db, bad) is None
