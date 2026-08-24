"""Regression tests for the division boundary.

Every bug guarded here produced a confident, wrong answer rather than an error:
a Premier League table containing 44 clubs, a promoted club's "last 5" spanning
two leagues, and an unknown division reported as "no data" instead of rejected.
"""
import os
import sys

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import Base, MatchResult
from db.teams import (
    CHAMPIONSHIP, TOP_FLIGHT, division_filter, is_played, resolve_division,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        # Coventry played in BOTH divisions — the club whose blended row ranked
        # first in a Premier League table on 46 games played.
        MatchResult(season="2025-26", matchweek=1, date="2026-01-01",
                    home_team="Arsenal", away_team="Chelsea",
                    home_goals=2, away_goals=1, division=TOP_FLIGHT),
        MatchResult(season="2025-26", matchweek=3, date="2026-01-08",
                    home_team="Coventry", away_team="Millwall",
                    home_goals=3, away_goals=0, division=CHAMPIONSHIP),
        MatchResult(season="2025-26", matchweek=4, date="2026-01-15",
                    home_team="Coventry", away_team="Hull",
                    home_goals=1, away_goals=1, division=CHAMPIONSHIP),
        # Written before the division column existed. NULL is top-flight and must
        # not disappear from reports — NULL fails an equality test in SQL.
        MatchResult(season="2019-20", matchweek=1, date="2019-08-10",
                    home_team="Liverpool", away_team="Norwich",
                    home_goals=4, away_goals=1, division=None),
        # Scheduled, not played.
        MatchResult(season="2026-27", matchweek=1, date="2026-09-01",
                    home_team="Arsenal", away_team="Spurs",
                    home_goals=None, away_goals=None, division=TOP_FLIGHT),
    ])
    session.commit()
    yield session
    session.close()


class TestDivisionFilter:
    def test_top_flight_excludes_championship(self, db):
        rows = division_filter(db.query(MatchResult), TOP_FLIGHT).all()
        teams = {r.home_team for r in rows}
        assert "Coventry" not in teams
        assert {"Arsenal", "Liverpool"} <= teams

    def test_championship_excludes_top_flight(self, db):
        rows = division_filter(db.query(MatchResult), CHAMPIONSHIP).all()
        assert {r.home_team for r in rows} == {"Coventry"}

    def test_null_division_counts_as_top_flight(self, db):
        """Legacy rows predate the column. Filtering them out would silently drop
        entire early seasons from every report."""
        rows = division_filter(db.query(MatchResult), TOP_FLIGHT).all()
        assert any(r.home_team == "Liverpool" for r in rows)

    def test_all_blends_only_when_asked(self, db):
        assert len(division_filter(db.query(MatchResult), "all").all()) == 5

    def test_a_club_in_both_divisions_is_counted_once_per_division(self, db):
        """The defect exactly: Coventry's two leagues summed into one row."""
        e0 = division_filter(db.query(MatchResult), TOP_FLIGHT).all()
        e1 = division_filter(db.query(MatchResult), CHAMPIONSHIP).all()
        assert sum(1 for r in e0 if r.home_team == "Coventry") == 0
        assert sum(1 for r in e1 if r.home_team == "Coventry") == 2


class TestDivisionValidation:
    """An unknown division fell through to `WHERE division = 'E7'`, matched
    nothing, and returned 'no played matches' — indistinguishable from a season
    that genuinely has none. A UI select rendered before its options loaded sent
    an empty string and got blank cards with no error anywhere."""

    def test_empty_means_default_not_no_data(self):
        assert resolve_division("") == TOP_FLIGHT
        assert resolve_division(None) == TOP_FLIGHT

    def test_known_divisions_pass_through(self):
        assert resolve_division("E0") == "E0"
        assert resolve_division("E1") == "E1"
        assert resolve_division("all") == "all"

    def test_unknown_division_is_rejected_not_silently_empty(self):
        with pytest.raises(HTTPException) as exc:
            resolve_division("E7")
        assert exc.value.status_code == 400
        assert "E7" in str(exc.value.detail)


class TestPlayedGuard:
    """Aggregates compare `home_goals > away_goals`; None raises TypeError in
    Python 3, so an in-progress season would crash the league endpoint."""

    def test_unplayed_fixture_is_not_played(self, db):
        row = db.query(MatchResult).filter(MatchResult.season == "2026-27").first()
        assert not is_played(row)

    def test_played_fixture_is_played(self, db):
        row = db.query(MatchResult).filter(MatchResult.home_team == "Arsenal",
                                           MatchResult.season == "2025-26").first()
        assert is_played(row)

    def test_comparing_an_unplayed_fixture_would_raise(self, db):
        """Documents why the guard exists rather than trusting callers."""
        row = db.query(MatchResult).filter(MatchResult.season == "2026-27").first()
        with pytest.raises(TypeError):
            _ = row.home_goals > row.away_goals


class TestChampionshipRounds:
    """football-data.co.uk carries no gameweek, so every E1 row sat at matchweek 0
    and any per-matchweek chart had a phantom round zero."""

    def test_rounds_are_derived_in_blocks_of_twelve(self):
        import pandas as pd

        from data.championship import MATCHES_PER_ROUND, derive_matchweeks

        df = pd.DataFrame({"date": [f"2025-08-{d:02d}" for d in range(1, 26)]})
        rounds = derive_matchweeks(df)
        assert rounds.min() == 1
        assert (rounds.iloc[:MATCHES_PER_ROUND] == 1).all()
        assert (rounds.iloc[MATCHES_PER_ROUND:MATCHES_PER_ROUND * 2] == 2).all()

    def test_rounds_follow_date_order_not_row_order(self):
        import pandas as pd

        from data.championship import derive_matchweeks

        df = pd.DataFrame({"date": ["2025-12-01", "2025-08-01", "2025-10-01"]})
        rounds = derive_matchweeks(df)
        # All three fall in the first block, but the helper must not reorder rows.
        assert list(rounds.index) == [0, 1, 2]
