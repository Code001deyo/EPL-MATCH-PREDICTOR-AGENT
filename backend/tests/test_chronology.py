"""P1 regression tests — chronological integrity.

The defect these guard against: dates were stored as 'DD/MM/YYYY' and every
rolling window filters with a string comparison, so '05/01/2026' sorted before
'31/12/2019'. Form windows, venue splits and the train/validation split were all
computed over mis-ordered matches, and "before this fixture" was not reliably
before — meaning the no-leakage requirement was not actually held.
"""
import os
import sys
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.features import _team_rolling, build_feature_vector
from data.ingestion import _parse_fixture


def _match(date, home, away, hg, ag):
    return {
        "id": 0, "season": "2025-26", "matchweek": 1, "date": date,
        "division": "E0", "stats_source": "test",
        "home_team": home, "away_team": away,
        "home_goals": hg, "away_goals": ag,
        "home_xg": None, "away_xg": None,
        "home_shots_ot": None, "away_shots_ot": None,
        "home_possession": None, "away_possession": None,
        "home_shots": None, "away_shots": None,
        "home_corners": None, "away_corners": None,
        "home_fouls": None, "away_fouls": None,
        "home_yellow_cards": None, "away_yellow_cards": None,
    }


def test_iso_dates_sort_across_year_boundary():
    """The exact comparison that was broken: January after the previous December."""
    dec = "2025-12-31"
    jan = "2026-01-05"
    assert dec < jan, "ISO dates must sort chronologically as strings"

    # The legacy format got this backwards, which is why a reseed is required.
    legacy_dec, legacy_jan = "31/12/2025", "05/01/2026"
    assert not (legacy_dec < legacy_jan), (
        "sanity check: the legacy format really did sort wrongly"
    )


def test_parse_fixture_emits_iso_dates():
    fixture = {
        "id": 1,
        "status": "C",
        "gameweek": {"gameweek": 1},
        "kickoff": {"millis": 1755284400000},  # 15 Aug 2025
        "teams": [
            {"team": {"shortName": "Arsenal"}, "score": 3},
            {"team": {"shortName": "Coventry"}, "score": 0},
        ],
    }
    parsed = _parse_fixture(fixture, "2025-26")
    assert parsed is not None
    date = parsed["date"]
    assert date.count("-") == 2 and "/" not in date, f"expected ISO, got {date!r}"
    year, month, day = date.split("-")
    assert len(year) == 4 and len(month) == 2 and len(day) == 2


def test_rolling_window_excludes_future_matches():
    """No-leakage: a window may only contain matches played strictly earlier."""
    df = pd.DataFrame([
        _match("2025-12-20", "Arsenal", "Chelsea", 2, 1),
        _match("2025-12-31", "Arsenal", "Everton", 1, 1),
        _match("2026-01-05", "Arsenal", "Fulham", 4, 0),   # after the cutoff
        _match("2026-02-10", "Arsenal", "Spurs", 3, 3),    # after the cutoff
    ])

    stats = _team_rolling(df, "Arsenal", before_date="2026-01-01")

    # Only the December matches qualify: 2+1 = 3 goals over 2 games.
    assert stats["avg_gf"] == pytest.approx(1.5), (
        f"window leaked future matches: avg_gf={stats['avg_gf']}"
    )
    # The 4-0 win on 05 Jan must not be visible.
    assert stats["avg_gf"] < 2.0


def test_feature_vector_is_leak_free_at_season_start():
    df = pd.DataFrame([
        _match("2025-08-16", "Arsenal", "Chelsea", 2, 0),
        _match("2025-08-23", "Arsenal", "Everton", 1, 0),
    ])
    feats = build_feature_vector(df, "Arsenal", "Chelsea", before_date="2025-08-16")
    # Nothing was played before the first fixture. Since P5 that reads as unknown
    # (NaN), not as zero — a team "scoring 0.0 and conceding 0.0" is a strong and
    # wrong signal, whereas NaN lets XGBoost learn a split for missingness.
    import math
    assert math.isnan(feats["home_form_pts"]), (
        f"expected unknown form to be NaN, got {feats['home_form_pts']}"
    )
    assert feats["home_top_flight_matches"] == 0
