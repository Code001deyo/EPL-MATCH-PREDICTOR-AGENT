"""The indexed feature build must agree with a full-frame scan, exactly.

`build_training_matrix` used to derive every window by filtering the whole match
frame — a dozen boolean scans per fixture. On the deployed dataset (11,218
matches, 4,570 of them training targets) that ran for about fifteen minutes
before the first estimator was fitted, so a retrain reported
`stage: "building feature matrix"` for long enough that operators read it as
"training never starts". Locally, over 6,545 matches, it measured 356 seconds.

`data/history.py` replaced the scans with one grouped index and a binary search.
That is only a safe trade if it selects *identical* rows, not merely similar
ones — a window that quietly includes one extra match is a leak, and a window
that drops one silently changes what the model learns.

So this module keeps the scan. `_scan_*` below are the original implementations,
preserved verbatim in behaviour, and the tests assert the indexed path matches
them over every team and every fixture date in a generated season. Comparing the
two is the only way this equivalence stays true as the index is maintained.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.features import _team_rolling, _mean, build_training_matrix
from data.history import MatchHistory


def _season(n_teams=8, rounds=6, seed=7):
    """A synthetic double round-robin with realistic gaps in the statistics.

    Missing values matter here: `_safe_mean` skipped NaN and `pts` scored a NaN
    result as zero, and the indexed path has to reproduce both.
    """
    rng = np.random.default_rng(seed)
    teams = [f"Team {chr(65 + i)}" for i in range(n_teams)]
    rows, day = [], 0
    for r in range(rounds):
        for i in range(0, n_teams, 2):
            home, away = teams[(i + r) % n_teams], teams[(i + r + 1) % n_teams]
            day += 3
            missing = rng.random() < 0.25      # a match with no statistics at all
            rows.append({
                "id": len(rows), "season": "2024-25", "matchweek": r + 1,
                "date": (pd.Timestamp("2024-08-01") + pd.Timedelta(days=day)).strftime("%Y-%m-%d"),
                "division": "E0" if rng.random() < 0.8 else "E1",
                "home_team": home, "away_team": away,
                "home_goals": int(rng.integers(0, 5)), "away_goals": int(rng.integers(0, 4)),
                "home_shots": np.nan if missing else float(rng.integers(5, 25)),
                "away_shots": np.nan if missing else float(rng.integers(5, 25)),
                "home_shots_ot": np.nan if missing else float(rng.integers(1, 10)),
                "away_shots_ot": np.nan if missing else float(rng.integers(1, 10)),
                "home_corners": np.nan if missing else float(rng.integers(0, 12)),
                "away_corners": np.nan if missing else float(rng.integers(0, 12)),
                "home_fouls": np.nan if missing else float(rng.integers(5, 18)),
                "away_fouls": np.nan if missing else float(rng.integers(5, 18)),
                "home_yellow_cards": np.nan if missing else float(rng.integers(0, 5)),
                "away_yellow_cards": np.nan if missing else float(rng.integers(0, 5)),
                "odds_home": None, "odds_draw": None, "odds_away": None,
            })
    return pd.DataFrame(rows).sort_values(["date", "id"]).reset_index(drop=True)


FRAME = _season()
TEAMS = sorted(set(FRAME["home_team"]) | set(FRAME["away_team"]))
DATES = list(FRAME["date"])


# --------------------------------------------------------------------------
# The pre-index implementations, kept as the reference to compare against.
# --------------------------------------------------------------------------

def _scan_rolling(df, team, before_date, window=5):
    home = df[(df["home_team"] == team) & (df["date"] < before_date)].tail(10).copy()
    away = df[(df["away_team"] == team) & (df["date"] < before_date)].tail(10).copy()
    total = int(len(df[(df["home_team"] == team) & (df["date"] < before_date)])
                + len(df[(df["away_team"] == team) & (df["date"] < before_date)]))

    def derive(frame, gf_c, ga_c, sot_c, shots_c, corners_c, fouls_c, yellows_c):
        gf, ga = frame[gf_c], frame[ga_c]
        out = pd.DataFrame({
            "date": frame["date"], "gf": gf, "ga": ga,
            "sot": frame[sot_c], "shots": frame[shots_c],
            "corners": frame[corners_c], "fouls": frame[fouls_c],
            "yellows": frame[yellows_c],
            "pts": np.where(gf > ga, 3, np.where(gf == ga, 1, 0)),
            "cs": (ga == 0).astype(int),
            "btts": ((frame["home_goals"] > 0) & (frame["away_goals"] > 0)).astype(int),
            "over25": ((frame["home_goals"] + frame["away_goals"]) > 2).astype(int),
        })
        return out

    home = derive(home, "home_goals", "away_goals", "home_shots_ot", "home_shots",
                  "home_corners", "home_fouls", "home_yellow_cards")
    away = derive(away, "away_goals", "home_goals", "away_shots_ot", "away_shots",
                  "away_corners", "away_fouls", "away_yellow_cards")
    combined = pd.concat([home, away]).sort_values("date", kind="stable")
    last5, last10 = combined.tail(window), combined.tail(10)
    if len(last5) == 0:
        return None
    return {
        "avg_gf": _mean(last5["gf"].to_numpy(float)),
        "avg_ga": _mean(last5["ga"].to_numpy(float)),
        "avg_sot": _mean(last5["sot"].to_numpy(float)),
        "avg_shots": _mean(last5["shots"].to_numpy(float)),
        "avg_corners": _mean(last5["corners"].to_numpy(float)),
        "avg_fouls": _mean(last5["fouls"].to_numpy(float)),
        "avg_yellows": _mean(last5["yellows"].to_numpy(float)),
        "form_pts": float(last5["pts"].sum()),
        "cs_rate": _mean(last5["cs"].to_numpy(float)),
        "btts_rate": _mean(last10["btts"].to_numpy(float)),
        "over_2_5_rate": _mean(last10["over25"].to_numpy(float)),
        "matches_played": total,
    }


def _scan_top_flight(df, team, before_date):
    return int(len(df[
        ((df["home_team"] == team) | (df["away_team"] == team))
        & (df["date"] < before_date)
        & (df["division"].fillna("E0") == "E0")
    ]))


def _scan_matches_in_window(df, team, before_date, days):
    cutoff = (pd.to_datetime(before_date) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    return float(len(df[
        ((df["home_team"] == team) | (df["away_team"] == team))
        & (df["date"] < before_date) & (df["date"] >= cutoff)
    ]))


def _same(a, b):
    if isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b):
        return True
    return a == pytest.approx(b, rel=1e-12, abs=1e-12)


# --------------------------------------------------------------------------

@pytest.mark.parametrize("team", TEAMS)
def test_rolling_windows_match_the_scan(team):
    index = MatchHistory(FRAME)
    from data.features import _rolling_stats

    for before in DATES:
        expected = _scan_rolling(FRAME, team, before)
        got = _rolling_stats(index.team_window(team, before))
        if expected is None:
            assert got["matches_played"] == 0
            assert np.isnan(got["form_pts"])
            continue
        for key, value in expected.items():
            assert _same(got[key], value), f"{team} @ {before}: {key}"


@pytest.mark.parametrize("team", TEAMS)
def test_counts_match_the_scan(team):
    index = MatchHistory(FRAME)
    for before in DATES:
        window = index.team_window(team, before)
        assert window.top_flight == _scan_top_flight(FRAME, team, before), (team, before)
        assert index.matches_within(team, before, 14) == _scan_matches_in_window(
            FRAME, team, before, 14), (team, before)


def test_team_rolling_still_takes_a_bare_frame():
    """The frame-only entry point is what tests/test_chronology.py exercises and
    what a caller holding no index gets. It must agree with the indexed path."""
    from data.features import _rolling_stats

    index = MatchHistory(FRAME)
    for team in TEAMS[:3]:
        for before in DATES[::5]:
            direct = _team_rolling(FRAME, team, before)
            indexed = _rolling_stats(index.team_window(team, before))
            assert direct.keys() == indexed.keys()
            for key in direct:
                assert _same(direct[key], indexed[key]), f"{team} @ {before}: {key}"


def test_build_reports_progress():
    """A retrain spends most of its life in this loop. Reporting only on entry
    left the operator watching a bar that could not tell working from wedged."""
    seen = []
    build_training_matrix(FRAME, on_progress=lambda stage, done, total: seen.append((stage, done, total)))
    assert seen, "the feature build reported no progress at all"
    stage, done, total = seen[-1]
    assert stage == "building feature matrix"
    assert done == total == len(FRAME[FRAME["division"].fillna("E0") == "E0"])
