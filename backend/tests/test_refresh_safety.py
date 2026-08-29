"""Regression tests for the refresh that deleted a season and put nothing back.

On 2026-08-29 the live instance came up, ran its boot refresh, and lost every
played fixture of the in-progress season. `refresh_current_season` deleted the
season's E0 rows and **committed**, then called the feed; the feed returned an
empty frame, `df["home_goals"]` raised `KeyError('home_goals')` because an empty
DataFrame has no columns, and the re-insert never ran. Stored count went from 14
to 0.

Nothing about that looked like a failure from outside. The error was appended to
a list in `/health/ready`, the app reported `ready: true`, and the season simply
had no matches in it.

The rule these tests hold to: **a refresh may never destroy stored rows unless it
has data in hand to replace them with.**
"""
import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db.database as database
from db.database import Base, MatchResult
from data import ingestion

SEASON = "2026-27"


def _stored(session, season=SEASON):
    return session.query(MatchResult).filter(
        MatchResult.season == season, MatchResult.division == "E0"
    ).count()


@pytest.fixture
def session(monkeypatch):
    """An in-memory database holding a part-played current season."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    live = Session()
    live.add_all([
        MatchResult(season=SEASON, matchweek=1, date=f"2026-08-{10 + i:02d}",
                    home_team=f"Home{i}", away_team=f"Away{i}",
                    home_goals=i % 3, away_goals=(i + 1) % 3,
                    division="E0", stats_source="pulselive")
        for i in range(14)
    ])
    # A Championship row, to confirm the E0 scoping still holds.
    live.add(MatchResult(season=SEASON, matchweek=1, date="2026-08-11",
                         home_team="Hull", away_team="Millwall",
                         home_goals=1, away_goals=1, division="E1",
                         stats_source="football-data"))
    live.commit()

    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setattr(ingestion, "_current_season_label", lambda: SEASON)
    monkeypatch.setattr(ingestion, "get_season_ids", lambda **kw: {SEASON: 999})
    yield live
    live.close()


def test_an_empty_feed_keeps_the_stored_season(session):
    """The exact production failure: the feed returns a frame with no columns."""
    with patch.object(ingestion, "load_season_from_api", return_value=pd.DataFrame()):
        ingestion.refresh_current_season()
    assert _stored(session) == 14


def test_a_feed_reporting_no_played_fixtures_keeps_them(session):
    """Results do not un-happen; a drop to zero played is a feed glitch."""
    unplayed = pd.DataFrame([{
        "season": SEASON, "matchweek": 2, "date": "2026-09-01",
        "home_team": "Home0", "away_team": "Away0",
        "home_goals": None, "away_goals": None,
    }])
    with patch.object(ingestion, "load_season_from_api", return_value=unplayed):
        ingestion.refresh_current_season()
    assert _stored(session) == 14


def test_a_failing_feed_keeps_the_stored_season(session):
    """A raising fetch must not have deleted anything on its way out."""
    with patch.object(ingestion, "load_season_from_api",
                      side_effect=RuntimeError("upstream down")):
        with pytest.raises(RuntimeError):
            ingestion.refresh_current_season()
    assert _stored(session) == 14


def test_a_good_feed_still_replaces_the_season(session):
    """The guard must not have broken the case refresh exists for."""
    fresh = pd.DataFrame([{
        "season": SEASON, "matchweek": 1, "date": f"2026-08-{10 + i:02d}",
        "home_team": f"Home{i}", "away_team": f"Away{i}",
        "home_goals": 2, "away_goals": 1,
    } for i in range(16)])          # two newly played matches
    with patch.object(ingestion, "load_season_from_api", return_value=fresh):
        written = ingestion.refresh_current_season()
    assert written == 16
    assert _stored(session) == 16
    # E1 is untouched — the delete stays scoped to the top flight.
    assert session.query(MatchResult).filter(
        MatchResult.season == SEASON, MatchResult.division == "E1"
    ).count() == 1
