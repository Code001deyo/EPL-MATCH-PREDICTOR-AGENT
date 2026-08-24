"""Tests for admin authentication, rate limiting and the prediction upsert.

Each guards a hole that was live on a public deployment: unauthenticated retrain
and refresh, an endpoint that let anyone rewrite the accuracy figures, no brake on
a public write endpoint, and a fixture gaining a new History row every time it was
predicted.
"""
import os
import sys
import time

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import auth
import ratelimit


class _StoredAdmin:
    """Stands in for the `admin_users` row auth now looks up."""

    def __init__(self, username="admin", epoch=1):
        self.username = username
        self.session_epoch = epoch
        self.password_hash = auth.hash_password("correct-horse-battery")


@pytest.fixture
def configured(monkeypatch):
    """A server with admin auth fully configured.

    The account moved from environment variables into the database, so these
    tests have to supply the stored row as well as the environment. They fake the
    two lookups rather than opening a database: what is under test here is the
    session and API-key logic, and pointing it at the developer's real SQLite file
    made the outcome depend on whether that file happened to have been migrated —
    which is exactly why these four tests were failing.
    """
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", auth.hash_password("correct-horse-battery"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret-not-used-anywhere-real")
    monkeypatch.setenv("ADMIN_API_KEY", "test-api-key")

    import db.adminuser as adminuser
    stored = _StoredAdmin()
    monkeypatch.setattr(adminuser, "has_admin", lambda _db: True)
    monkeypatch.setattr(
        adminuser, "get_by_username",
        lambda _db, name: stored if name == stored.username else None,
    )
    yield stored


class FakeRequest:
    """Minimal stand-in — require_admin only reads cookies and headers."""

    def __init__(self, cookies=None, headers=None):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.client = None


class TestPasswordHashing:
    def test_roundtrip(self):
        assert auth.verify_password("hunter2", auth.hash_password("hunter2"))

    def test_wrong_password_rejected(self):
        assert not auth.verify_password("wrong", auth.hash_password("hunter2"))

    def test_hash_is_salted(self):
        """Two hashes of the same password must differ, or identical passwords are
        visible as identical hashes."""
        assert auth.hash_password("same") != auth.hash_password("same")

    @pytest.mark.parametrize("bad", ["", "notahash", "bcrypt$aa$bb", "scrypt$zz", "scrypt$nothex$nothex"])
    def test_malformed_hash_is_a_failure_not_a_crash(self, bad):
        """A corrupted env var must deny access, never raise past the handler and
        never accidentally pass."""
        assert auth.verify_password("anything", bad) is False


class TestStaleSession:
    """A session signed at an old epoch must be refused even though its signature
    is perfectly valid — this is what makes a password change sign others out."""

    def test_superseded_epoch_is_rejected(self, configured):
        token = auth.issue_session("admin", configured.session_epoch)
        configured.session_epoch += 1          # as a password change would do
        with pytest.raises(HTTPException) as exc:
            auth.require_admin(FakeRequest(cookies={auth.COOKIE_NAME: token}))
        assert exc.value.status_code == 401


class TestFailsClosed:
    """The property that matters most: an unconfigured server must deny admin
    actions, not allow them."""

    def test_unconfigured_is_not_configured(self, monkeypatch):
        for var in ("ADMIN_USERNAME", "ADMIN_PASSWORD_HASH", "SESSION_SECRET"):
            monkeypatch.delenv(var, raising=False)
        assert auth.is_configured() is False

    def test_require_admin_raises_503_when_unconfigured(self, monkeypatch):
        for var in ("ADMIN_USERNAME", "ADMIN_PASSWORD_HASH", "SESSION_SECRET"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(HTTPException) as exc:
            auth.require_admin(FakeRequest())
        assert exc.value.status_code == 503

    def test_partial_configuration_still_fails_closed(self, monkeypatch):
        """A username with no secret must not count as configured."""
        monkeypatch.setenv("ADMIN_USERNAME", "admin")
        monkeypatch.delenv("SESSION_SECRET", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
        assert auth.is_configured() is False


class TestSessions:
    def test_valid_session_is_accepted(self, configured):
        token = auth.issue_session("admin", configured.session_epoch)
        assert auth.require_admin(FakeRequest(cookies={auth.COOKIE_NAME: token})) == "admin"

    def test_no_cookie_is_401(self, configured):
        with pytest.raises(HTTPException) as exc:
            auth.require_admin(FakeRequest())
        assert exc.value.status_code == 401

    def test_tampered_token_is_rejected(self, configured):
        token = auth.issue_session("admin", configured.session_epoch)
        tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
        assert auth.read_session(tampered) is None

    def test_token_signed_with_another_secret_is_rejected(self, configured, monkeypatch):
        """The signature, not the shape of the token, is what is trusted."""
        token = auth.issue_session("admin", configured.session_epoch)
        monkeypatch.setenv("SESSION_SECRET", "a-completely-different-secret")
        assert auth.read_session(token) is None

    def test_expired_token_is_rejected(self, configured, monkeypatch):
        token = auth.issue_session("admin", configured.session_epoch)
        monkeypatch.setattr(auth, "SESSION_MAX_AGE", -1)
        assert auth.read_session(token) is None


class TestApiKey:
    """The scheduled refresh workflow cannot hold a cookie."""

    def test_correct_key_authenticates(self, configured):
        req = FakeRequest(headers={"X-Admin-Key": "test-api-key"})
        assert auth.require_admin(req) == "api-key"

    def test_wrong_key_is_rejected(self, configured):
        req = FakeRequest(headers={"X-Admin-Key": "not-the-key"})
        with pytest.raises(HTTPException) as exc:
            auth.require_admin(req)
        assert exc.value.status_code == 401

    def test_empty_key_env_does_not_authenticate_empty_header(self, configured, monkeypatch):
        """With no key configured, sending an empty header must not match it."""
        monkeypatch.setenv("ADMIN_API_KEY", "")
        with pytest.raises(HTTPException):
            auth.require_admin(FakeRequest(headers={"X-Admin-Key": ""}))


class TestRateLimit:
    def setup_method(self):
        ratelimit.reset()

    def _req(self, ip="1.2.3.4"):
        return FakeRequest(headers={"x-forwarded-for": ip})

    def test_allows_up_to_capacity_then_429s(self):
        req = self._req()
        for _ in range(3):
            ratelimit.limit(req, "t", capacity=3, per_seconds=60)
        with pytest.raises(HTTPException) as exc:
            ratelimit.limit(req, "t", capacity=3, per_seconds=60)
        assert exc.value.status_code == 429
        assert "Retry-After" in exc.value.headers

    def test_buckets_are_per_client(self):
        """One heavy user must not lock everyone else out."""
        for _ in range(3):
            ratelimit.limit(self._req("1.1.1.1"), "t", capacity=3, per_seconds=60)
        ratelimit.limit(self._req("2.2.2.2"), "t", capacity=3, per_seconds=60)

    def test_buckets_are_per_endpoint(self):
        for _ in range(3):
            ratelimit.limit(self._req(), "predict", capacity=3, per_seconds=60)
        ratelimit.limit(self._req(), "login", capacity=3, per_seconds=60)

    def test_refills_over_time(self):
        req = self._req()
        for _ in range(2):
            ratelimit.limit(req, "t", capacity=2, per_seconds=0.2)
        time.sleep(0.25)
        ratelimit.limit(req, "t", capacity=2, per_seconds=0.2)

    def test_forwarded_for_is_preferred_over_the_proxy_address(self):
        """Render and Vercel both sit in front; keying on the socket address would
        rate-limit every visitor as though they were one caller."""
        assert ratelimit.client_ip(self._req("9.9.9.9")) == "9.9.9.9"

    def test_forwarded_for_uses_the_leftmost_entry(self):
        req = FakeRequest(headers={"x-forwarded-for": "5.5.5.5, 10.0.0.1, 10.0.0.2"})
        assert ratelimit.client_ip(req) == "5.5.5.5"
