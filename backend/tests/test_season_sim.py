"""What must hold about a season simulation, whatever the model says.

These are arithmetic identities, not model quality checks. Exactly one club wins
the league in every simulated season, exactly four finish in the top four, exactly
three go down — so those probabilities must sum to 1, 4 and 3 across the division.
If they do not, the ranking is wrong, and a ranking bug would be invisible in the
UI: twenty plausible-looking percentages that happen not to describe any set of
seasons.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import Base, MatchResult  # noqa: E402
from db import race as race_db  # noqa: E402
from models import season_sim  # noqa: E402

TEAMS = [f"Club {chr(65 + i)}" for i in range(20)]


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/sim.db",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _flat_table():
    """Twenty clubs, all level. Any asymmetry in the result is a bug in the code."""
    return {t: {"team": t, "points": 0, "played": 0, "scored": 0, "conceded": 0,
                "goal_difference": 0} for t in TEAMS}


def _round_robin(rate=1.4):
    """One fixture between every pair, all with identical scoring rates."""
    return [(h, a, rate, rate) for i, h in enumerate(TEAMS) for a in TEAMS[i + 1:]]


def test_exactly_one_club_wins_the_league(db):
    out = season_sim.simulate(_flat_table(), _round_robin(), simulations=2000, seed=1)
    assert round(sum(t["title_prob"] for t in out), 6) == 1.0


def test_exactly_four_finish_in_the_top_four(db):
    out = season_sim.simulate(_flat_table(), _round_robin(), simulations=2000, seed=1)
    assert round(sum(t["top_four_prob"] for t in out), 6) == 4.0


def test_exactly_three_are_relegated(db):
    out = season_sim.simulate(_flat_table(), _round_robin(), simulations=2000, seed=1)
    assert round(sum(t["relegation_prob"] for t in out), 6) == 3.0


def test_an_unassailable_lead_is_reported_as_certain(db):
    """A club that cannot be caught must read 100%, not 'very likely'.

    One club 200 points clear with a single fixture left. No sampling of that
    fixture can change the order, so any answer below 1.0 means the ranking is
    not actually driven by points.
    """
    table = _flat_table()
    table[TEAMS[0]]["points"] = 200

    out = season_sim.simulate(table, [(TEAMS[1], TEAMS[2], 1.4, 1.4)],
                              simulations=500, seed=3)
    champion = next(t for t in out if t["team"] == TEAMS[0])
    assert champion["title_prob"] == 1.0
    assert champion["relegation_prob"] == 0.0


def test_a_club_that_cannot_catch_up_is_reported_as_zero(db):
    """Eliminated means 0%, not a rounded-down small number."""
    table = _flat_table()
    table[TEAMS[0]]["points"] = 200
    out = season_sim.simulate(table, [], simulations=500, seed=3)
    assert all(t["title_prob"] == 0.0 for t in out if t["team"] != TEAMS[0])


def test_goal_difference_breaks_a_tie_on_points(db):
    """The real Premier League order, not an alphabetical or arbitrary one."""
    table = _flat_table()
    table[TEAMS[0]]["points"] = table[TEAMS[1]]["points"] = 50
    table[TEAMS[0]]["goal_difference"] = 30
    table[TEAMS[1]]["goal_difference"] = 5

    out = season_sim.simulate(table, [], simulations=200, seed=5)
    by_team = {t["team"]: t for t in out}
    assert by_team[TEAMS[0]]["title_prob"] == 1.0
    assert by_team[TEAMS[1]]["title_prob"] == 0.0


def test_the_same_seed_gives_the_same_answer(db):
    """The curve must move because results changed, not because dice were rerolled."""
    a = season_sim.simulate(_flat_table(), _round_robin(), simulations=500, seed=42)
    b = season_sim.simulate(_flat_table(), _round_robin(), simulations=500, seed=42)
    assert [t["title_prob"] for t in a] == [t["title_prob"] for t in b]


def test_an_unplayed_fixture_is_not_counted_as_a_draw(db):
    """A scheduled match has no result; it must not become 0-0 in the table."""
    db.add_all([
        MatchResult(season="2026-27", matchweek=1, date="2026-08-15", division="E0",
                    home_team="Club A", away_team="Club B", home_goals=2, away_goals=0),
        MatchResult(season="2026-27", matchweek=2, date="2026-08-22", division="E0",
                    home_team="Club A", away_team="Club C", home_goals=None, away_goals=None),
    ])
    db.commit()

    table = season_sim.current_table(db, "2026-27")
    assert table["Club A"]["played"] == 1
    assert table["Club A"]["points"] == 3
    assert "Club C" not in table, "a club with no played match must not appear on points"


# --- snapshots ------------------------------------------------------------

def _snapshot_rows(prob):
    return [{"team": "Club A", "title_prob": prob, "top_four_prob": 0.9,
             "relegation_prob": 0.0, "points": 9, "played": 3,
             "goal_difference": 5, "projected_points": 78.0}]


def test_a_live_snapshot_supersedes_a_reconstruction_of_the_same_week(db):
    """Both are stored; only one is served.

    The backfill reconstructs every completed matchweek including the one just
    simulated live. Serving both returned every club twice and made the
    week-on-week delta compare a live figure against a reconstruction of itself.
    """
    race_db.save_snapshot(db, "2026-27", 3, _snapshot_rows(0.40),
                          kind=race_db.KIND_BACKFILL)
    race_db.save_snapshot(db, "2026-27", 3, _snapshot_rows(0.45),
                          kind=race_db.KIND_LIVE)

    points = race_db.series(db, "2026-27")
    assert len(points) == 1
    assert points[0]["kind"] == race_db.KIND_LIVE
    assert points[0]["title_prob"] == 0.45


def test_rerunning_a_backfill_replaces_rather_than_stacks(db):
    """Otherwise a repeated backfill invents wobble in the curve."""
    race_db.save_snapshot(db, "2026-27", 2, _snapshot_rows(0.30), kind=race_db.KIND_BACKFILL)
    race_db.save_snapshot(db, "2026-27", 2, _snapshot_rows(0.31), kind=race_db.KIND_BACKFILL)

    points = race_db.series(db, "2026-27")
    assert len(points) == 1
    assert points[0]["title_prob"] == 0.31
