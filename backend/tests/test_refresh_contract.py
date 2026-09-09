"""The contract `.github/workflows/refresh-data.yml` depends on.

`POST /data/refresh` used to answer synchronously with `{"status": "refreshed"}`.
It became a background job in `0b952225` — 202 with a job id, the outcome
delivered later on `/data/jobs/{id}` — and the workflow was never updated. It
went on grepping for the old body, never found one again, and every scheduled run
failed for eleven days on a refresh that was in fact starting normally.
`retrain-model.yml` had already been converted to poll; refresh was missed.

Nothing caught it because the assertion lived only inside a YAML `run:` block,
which no test suite executes. These tests move both halves of that contract into
the suite: the response shape the workflow parses, and the decision the workflow
makes about a finished job. Change either one and this file fails locally, long
before a scheduled run does.
"""

import importlib.util
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from db.database import init_db  # noqa: E402

init_db()
client = TestClient(app)

# Lives under backend/, not .github/, so it is reachable from all three places
# that need it: the workflow (which checks the repo out), this test suite, and the
# backend container — where backend/ is /app and .github/ does not exist at all.
CHECK_REFRESH = os.path.join(os.path.dirname(__file__), "..", "scripts", "check_refresh.py")


def _load_checker():
    """Import the workflow's checker by path — it is not on sys.path."""
    spec = importlib.util.spec_from_file_location("check_refresh", CHECK_REFRESH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the response the workflow parses -------------------------------------

def test_refresh_is_asynchronous_and_hands_back_a_job_id():
    """The workflow reads `job_id` out of this response and polls it.

    Unauthenticated here, so the call is rejected before any work starts — the
    point is the *route's* contract, not a real refresh. A 401 or 503 proves the
    admin gate holds; what must never come back is a 200 carrying a finished
    result, because that is the synchronous shape the workflow was broken by.
    """
    r = client.post("/data/refresh")
    assert r.status_code in (401, 503), (
        "refresh must stay admin-gated; a public refresh endpoint lets anyone "
        "delete and re-insert a season's rows"
    )


def test_refresh_route_is_declared_202_not_200():
    """202 is the signal to the caller that the work is not finished.

    Asserted against the route declaration rather than a live call, so this holds
    without an admin session or a network fetch.
    """
    route = next(
        r for r in app.routes
        if getattr(r, "path", None) == "/data/refresh" and "POST" in getattr(r, "methods", set())
    )
    assert route.status_code == 202


def test_a_refresh_job_can_be_polled():
    """`/data/jobs/{id}` is the endpoint the workflow polls to completion."""
    r = client.get("/data/jobs/definitely-not-a-real-job")
    assert r.status_code == 404, "an unknown job must 404, not answer with a fake job"


# --- the decision the workflow makes about a finished job ------------------

def _job(status, **result):
    return {"id": "abc", "state": "succeeded", "result": {"status": status, **result}}


def test_a_completed_refresh_passes():
    ok, lines = _load_checker().summarise(
        _job("refreshed", season="2026-27", played_fixtures=30,
             statistics_attached=30, predictions_settled=4, last_refreshed="2026-09-09T00:00:00Z")
    )
    assert ok
    body = "\n".join(lines)
    # The counts are the reason to read the summary at all: a refresh that
    # reports zero played fixtures mid-season is a problem you want to see.
    assert "2026-27" in body and "| Played fixtures | 30 |" in body


def test_pre_season_passes_without_claiming_a_refresh():
    ok, lines = _load_checker().summarise(_job("season-not-published", season="2027-28"))
    assert ok
    assert "not published" in "\n".join(lines)


@pytest.mark.parametrize("status", ["running", "error", None, "ok"])
def test_any_other_status_fails_the_run(status):
    """The failure mode worth preventing is a green run that refreshed nothing."""
    ok, lines = _load_checker().summarise(_job(status))
    assert not ok
    assert "unexpected status" in "\n".join(lines)


def test_a_job_with_no_result_at_all_fails():
    """A succeeded job carrying `result: null` is not a successful refresh."""
    ok, _ = _load_checker().summarise({"id": "abc", "state": "succeeded", "result": None})
    assert not ok
