"""The re-seed guards must repair narrowly, never wipe the database.

These exist because the unscoped version took production down. Extending the
history to 2005-06 put one Premier League season with a matchweek above 38 into
the table; the guard responded by deleting every row of every division and
season, and the site served no predictions at all until a 22-season re-ingest
finished. The re-seed restored whatever tripped the guard, so the next restart
did it again.

The guard was not wrong to notice. It was wrong to answer with DELETE FROM
match_results.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.ingestion import _corrupt_matchweek_seasons, _legacy_date_seasons
from db.database import Base, MatchResult


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _add(db, season, division, matchweek, date="2026-01-01"):
    db.add(MatchResult(season=season, division=division, matchweek=matchweek,
                       date=date, home_team="A", away_team="B",
                       home_goals=1, away_goals=0))
    db.commit()


class TestMatchweekGuard:
    def test_names_only_the_offending_season(self, db):
        _add(db, "2005-06", "E0", 200)
        _add(db, "2024-25", "E0", 38)
        assert _corrupt_matchweek_seasons(db) == ["2005-06"]

    @pytest.mark.parametrize("season,high", [
        ("2006-07", 39), ("2008-09", 39), ("2012-13", 39), ("2013-14", 40),
    ])
    def test_rearranged_top_flight_seasons_are_not_corruption(self, db, season, high):
        """The bug that caused the outage, pinned to the real seasons.

        The Premier League's own gameweek numbering runs past 38 when matches are
        rearranged. These four seasons carry a full, correct 380 fixtures and were
        being deleted - along with every other season - on every restart."""
        _add(db, season, "E0", high)
        assert _corrupt_matchweek_seasons(db) == []

    def test_silent_on_a_healthy_table(self, db):
        _add(db, "2024-25", "E0", 38)
        assert _corrupt_matchweek_seasons(db) == []

    def test_championship_46_rounds_are_not_corruption(self, db):
        """The Championship plays 46. Flagging that wiped the table on every boot
        once - the query is scoped to E0 so it cannot happen again."""
        _add(db, "2024-25", "E1", 46)
        assert _corrupt_matchweek_seasons(db) == []

    def test_a_bad_season_does_not_implicate_a_good_one(self, db):
        """The property that was violated in production: the blast radius of one
        bad season must be that season."""
        _add(db, "2005-06", "E0", 300)
        _add(db, "2012-13", "E0", 38)
        _add(db, "2024-25", "E0", 38)
        assert _corrupt_matchweek_seasons(db) == ["2005-06"]

    def test_null_matchweeks_are_not_corruption(self, db):
        _add(db, "2026-27", "E0", None)
        assert _corrupt_matchweek_seasons(db) == []

    def test_multiple_bad_seasons_are_all_reported(self, db):
        _add(db, "2005-06", "E0", 120)
        _add(db, "2007-08", "E0", 90)
        _add(db, "2024-25", "E0", 38)
        assert _corrupt_matchweek_seasons(db) == ["2005-06", "2007-08"]


class TestLegacyDateGuard:
    def test_names_only_the_season_holding_a_slash_date(self, db):
        _add(db, "2005-06", "E0", 10, date="15/08/2005")
        _add(db, "2024-25", "E0", 10, date="2025-08-15")
        assert _legacy_date_seasons(db) == ["2005-06"]

    def test_silent_when_every_date_is_iso(self, db):
        _add(db, "2024-25", "E0", 10, date="2025-08-15")
        assert _legacy_date_seasons(db) == []

    def test_covers_every_division(self, db):
        """Unlike the matchweek guard this is not scoped to E0 - a day-first date
        sorts wrongly wherever it appears."""
        _add(db, "2024-25", "E1", 10, date="15/08/2024")
        assert _legacy_date_seasons(db) == ["2024-25"]
