import pytest
from fastapi.testclient import TestClient
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app
from db.database import init_db

# Create the schema before any request is made.
#
# `main.py` calls init_db() from an on_event("startup") handler, and a
# module-level `TestClient(app)` never fires startup — that only happens when the
# client is used as a context manager. So every endpoint that touched a table
# raised "no such table: match_results" and four of these tests failed on a clean
# checkout. CI has been red on every commit since 2026-08-24 for this reason
# alone, which meant the suite was not gating anything: a genuine regression would
# have looked exactly like the failure that was already there.
#
# The tables are wanted empty, not seeded. These tests assert the *shape* of a
# response — that /teams answers 200 with a "teams" key — and an empty database is
# the honest case for that: it is what a freshly deployed instance serves before
# ingestion finishes, and the endpoints are supposed to cope with it.
init_db()

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_reports_the_running_commit(monkeypatch):
    """/health must say which code is answering.

    The deploy workflow compares this against the SHA it pushed. Without it,
    "deployed" and "restarted" are indistinguishable from outside — which is how
    two pushes sat undeployed for an hour on 2026-08-29 while a CPU-variance
    latency reading was mistaken for the new code working.
    """
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123def456")
    assert client.get("/health").json()["commit"] == "abc123def456"


def test_health_commit_is_unknown_when_unset(monkeypatch):
    """Absent means absent — never a value that reads as a real answer."""
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    assert client.get("/health").json()["commit"] == "unknown"


def test_get_teams():
    r = client.get("/teams")
    assert r.status_code == 200
    assert "teams" in r.json()


def test_recent_fixtures():
    r = client.get("/fixtures/recent")
    assert r.status_code == 200
    assert "fixtures" in r.json()


def test_prediction_history_empty():
    r = client.get("/predictions/history")
    assert r.status_code == 200
    assert "predictions" in r.json()


def test_predict_missing_model():
    r = client.post("/predict", json={
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "matchweek": 1,
        "season": "2024-25"
    })
    assert r.status_code in (200, 400, 503)


def test_results_endpoint_is_gone():
    """POST /results is removed, not merely protected.

    It took a prediction id and a scoreline and wrote them straight into the
    actual result, with no authentication — so any caller could rewrite the
    accuracy figures the dashboard reports. Settlement already derives actual
    results from real match data, so the endpoint had no legitimate use.

    This asserted 404 before too, but for the opposite reason: the endpoint
    existed and the prediction id did not. Sending a valid-looking body proves the
    route itself is absent rather than just rejecting that id.
    """
    r = client.post("/results", json={
        "prediction_id": 1,
        "actual_home": 9,
        "actual_away": 0,
    })
    assert r.status_code == 404
    assert "/results" not in [route.path for route in app.routes]


def test_admin_endpoints_are_not_public():
    """Retrain, backtest and refresh were all unauthenticated. Retrain burns ~250s
    of CPU on a 0.1 vCPU instance, so leaving it open was a denial-of-service
    button as much as an integrity problem."""
    for path in ("/model/retrain", "/model/backtest/run", "/data/refresh"):
        r = client.post(path)
        # 401 when admin auth is configured, 503 when it is not. Never 2xx, and
        # never 202 — an anonymous caller must not be able to start a job.
        assert r.status_code in (401, 503), f"{path} returned {r.status_code}"
