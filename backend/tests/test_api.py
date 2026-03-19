import pytest
from fastapi.testclient import TestClient
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


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


def test_submit_result_not_found():
    r = client.post("/results", json={
        "prediction_id": 99999,
        "actual_home": 2,
        "actual_away": 1
    })
    assert r.status_code == 404
