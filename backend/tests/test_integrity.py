"""Regression tests for the data-integrity defects found in the D1 pass.

Both bugs produced a plausible-looking result rather than an error: a prediction
that sat "pending" beside a played match, and a team picker that offered fixtures
which cannot exist. Neither was caught by the existing suite.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import Base, MatchResult, Prediction
from db.settlement import settle_predictions
from db.teams import is_top_flight, top_flight_teams


@pytest.fixture
def db():
    """In-memory database seeded with the exact shape that broke settlement."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        # The real fixture, stored at matchweek 31 — played, 2-2.
        MatchResult(season="2025-26", matchweek=31, date="2026-03-20",
                    home_team="Bournemouth", away_team="Man Utd",
                    home_goals=2, away_goals=2, division="E0"),
        # An unplayed top-flight fixture: must never be settled.
        MatchResult(season="2026-27", matchweek=1, date="2026-08-30",
                    home_team="Fulham", away_team="Chelsea",
                    home_goals=None, away_goals=None, division="E0"),
        # Championship history for a promoted club — feature input, not selectable.
        MatchResult(season="2025-26", matchweek=0, date="2025-08-09",
                    home_team="Wrexham", away_team="Millwall",
                    home_goals=1, away_goals=0, division="E1"),
    ])
    session.commit()
    yield session
    session.close()


class TestSettlementIgnoresMatchweek:
    """The prediction was submitted as MW35; ingestion had stored the fixture at
    MW31. Joining on matchweek meant it could never settle."""

    def test_disagreeing_matchweek_still_settles(self, db):
        db.add(Prediction(fixture="Bournemouth vs Man Utd", season="2025-26",
                          matchweek=35, predicted_home=1, predicted_away=1))
        db.commit()

        assert settle_predictions(db) == 1

        p = db.query(Prediction).first()
        assert (p.actual_home, p.actual_away) == (2, 2)

    def test_settling_corrects_the_matchweek(self, db):
        """Otherwise History keeps displaying MW35 for a match played in MW31."""
        db.add(Prediction(fixture="Bournemouth vs Man Utd", season="2025-26",
                          matchweek=35, predicted_home=1, predicted_away=1))
        db.commit()
        settle_predictions(db)
        assert db.query(Prediction).first().matchweek == 31

    def test_unplayed_fixture_is_left_alone(self, db):
        """A pending prediction is only wrong when the match has been played."""
        db.add(Prediction(fixture="Fulham vs Chelsea", season="2026-27",
                          matchweek=1, predicted_home=1, predicted_away=2))
        db.commit()

        assert settle_predictions(db) == 0
        assert db.query(Prediction).first().actual_home is None

    def test_wrong_season_does_not_settle(self, db):
        """Dropping matchweek must not loosen the key to the point of collisions."""
        db.add(Prediction(fixture="Bournemouth vs Man Utd", season="2019-20",
                          matchweek=31, predicted_home=1, predicted_away=1))
        db.commit()
        assert settle_predictions(db) == 0

    def test_never_settles_against_a_championship_result(self, db):
        """promoted.py stores E1 rows; a live prediction must not resolve to one."""
        db.add(Prediction(fixture="Wrexham vs Millwall", season="2025-26",
                          matchweek=0, predicted_home=0, predicted_away=0))
        db.commit()
        assert settle_predictions(db) == 0


class TestTeamListIsTopFlightOnly:
    """/teams was a bare distinct() with no division filter, so it offered 47
    clubs — including sides that have never played a Premier League match."""

    def test_championship_only_clubs_are_excluded(self, db):
        teams = top_flight_teams(db)
        assert "Wrexham" not in teams
        assert "Millwall" not in teams

    def test_top_flight_clubs_are_included(self, db):
        teams = top_flight_teams(db)
        assert {"Bournemouth", "Man Utd", "Fulham", "Chelsea"} <= set(teams)

    def test_away_only_club_is_not_missed(self, db):
        """A home-only scan would drop a club that only appears as the away side."""
        assert "Man Utd" in top_flight_teams(db)

    def test_promoted_club_becomes_selectable_once_it_has_a_top_flight_row(self, db):
        """Coventry and Hull are E1 history AND 2026-27 Premier League clubs.
        Filtering on division, not on a hardcoded list, is what lets a promoted
        side appear the moment it actually plays a top-flight match."""
        assert not is_top_flight(db, "Coventry")
        db.add(MatchResult(season="2026-27", matchweek=1, date="2026-08-21",
                           home_team="Arsenal", away_team="Coventry",
                           home_goals=3, away_goals=0, division="E0"))
        db.commit()
        assert is_top_flight(db, "Coventry")

    def test_unknown_club_is_not_top_flight(self, db):
        assert not is_top_flight(db, "Nobody FC")
