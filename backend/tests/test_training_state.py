"""When the model counts as stale.

This decides whether a scheduled job spends ten minutes of a 0.1 vCPU instance
retraining. Both mistakes are expensive in different ways: never firing leaves
the model on last month's data with nothing on the site saying so, and firing
every day burns the instance producing identical estimators.

The watermark also has to survive the thing that resets it. The free tier has no
persistent disk, so a deploy restores the baked seed models and the watermark
goes with them - after which the running model really is the older one and really
does need retraining. That is the behaviour asserted here, not worked around.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import Base, MatchResult  # noqa: E402
from models import training_state  # noqa: E402

SEASON = "2026-27"


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/state.db",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Never read or write the real saved_models directory from a test."""
    monkeypatch.setattr(training_state, "STATE_PATH", str(tmp_path / "training_state.json"))
    monkeypatch.setattr(training_state, "MODEL_DIR", str(tmp_path))


def _matchweek(db, matchweek, played=10, season=SEASON):
    for i in range(played):
        db.add(MatchResult(
            season=season, matchweek=matchweek, date=f"2026-08-{10 + matchweek:02d}",
            division="E0", home_team=f"H{matchweek}-{i}", away_team=f"A{matchweek}-{i}",
            home_goals=1, away_goals=0,
        ))
    db.commit()


# --- what counts as a completed matchweek --------------------------------

def test_a_fully_played_matchweek_counts(db):
    _matchweek(db, 1)
    assert training_state.completed_matchweek(db, SEASON) == 1


def test_a_matchweek_with_one_postponement_still_counts(db):
    """Nine played of ten is enough new evidence to train on.

    Requiring all ten would let a single postponed fixture hold the season's
    watermark back for a week, and the nine that were played are real.
    """
    _matchweek(db, 1)
    _matchweek(db, 2, played=9)
    assert training_state.completed_matchweek(db, SEASON) == 2


def test_a_matchweek_barely_started_does_not_count(db):
    _matchweek(db, 1)
    _matchweek(db, 2, played=2)
    assert training_state.completed_matchweek(db, SEASON) == 1


def test_unplayed_fixtures_are_not_counted(db):
    _matchweek(db, 1)
    for i in range(10):
        db.add(MatchResult(season=SEASON, matchweek=2, date="2026-08-20", division="E0",
                           home_team=f"H2-{i}", away_team=f"A2-{i}",
                           home_goals=None, away_goals=None))
    db.commit()
    assert training_state.completed_matchweek(db, SEASON) == 1, (
        "a scheduled fixture has not been played, so it is not evidence to train on"
    )


# --- staleness ------------------------------------------------------------

def test_a_model_that_was_never_stamped_is_stale(db):
    """A deploy restores the baked models and clears the watermark.

    That must read as stale: the running model is the older baked one.
    """
    _matchweek(db, 1)
    state = training_state.staleness(db, SEASON)
    assert state["stale"] is True
    assert state["trained_through_matchweek"] is None


def test_a_model_trained_through_the_latest_week_is_not_stale(db):
    _matchweek(db, 1)
    _matchweek(db, 2)
    training_state.write_state(SEASON, 2)

    state = training_state.staleness(db, SEASON)
    assert state["stale"] is False
    assert state["behind_by"] == 0


def test_a_new_matchweek_makes_it_stale_again(db):
    _matchweek(db, 1)
    training_state.write_state(SEASON, 1)
    assert training_state.staleness(db, SEASON)["stale"] is False

    _matchweek(db, 2)
    state = training_state.staleness(db, SEASON)
    assert state["stale"] is True
    assert state["behind_by"] == 1


def test_last_seasons_watermark_does_not_vouch_for_this_one(db):
    """August, a new campaign, and a model trained through last May.

    Without the season check the watermark would read 38 against a completed
    matchweek of 1 and the model would never retrain all season.
    """
    _matchweek(db, 1)
    training_state.write_state("2025-26", 38)

    state = training_state.staleness(db, SEASON)
    assert state["stale"] is True
    assert state["trained_through_matchweek"] is None


def test_a_season_with_nothing_played_is_not_stale(db):
    """Pre-season is not a reason to retrain: there is no new evidence."""
    assert training_state.staleness(db, SEASON)["stale"] is False


def test_a_corrupt_watermark_reads_as_never_trained(db):
    """Failing closed here means one redundant retrain, which is cheap.

    Failing open would mean never retraining, which is silent.
    """
    _matchweek(db, 1)
    with open(training_state.STATE_PATH, "w", encoding="utf-8") as fh:
        fh.write("{ not json")

    assert training_state.staleness(db, SEASON)["stale"] is True
