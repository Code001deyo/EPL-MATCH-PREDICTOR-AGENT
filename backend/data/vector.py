"""One fixture's feature vector.

Split out of `features.py`, which had grown past the project's ~200-line
convention with three separable jobs in it: loading the match frame, computing a
fixture's features, and assembling the training matrix. This module is the
middle one — everything that turns "these two clubs, this date" into the numbers
the estimator sees.

It computes; it does not search. Finding the rows a fixture may look at belongs
to `data/history.py`, and the separation is the point: every helper here reads a
window that has already been cut at the fixture's kickoff, so none of them can
reintroduce a scan of the full frame or reach past the cutoff.
"""
from __future__ import annotations

import numpy as np

from .calibration import translate, prior_weight
from .strength import StrengthIndex, strength_features
from .odds import odds_feature_dict
from . import history
from .history import MatchHistory

# Rolling features produced per team. Kept as a named list so an unknown team
# yields exactly this set as NaN — no silent shape mismatch between the
# known-team and unknown-team paths.
ROLLING_FEATURES = [
    "avg_gf", "avg_ga", "shot_accuracy", "avg_sot", "avg_shots",
    "avg_corners", "avg_fouls", "avg_yellows", "form_pts",
    "cs_rate", "btts_rate", "over_2_5_rate",
]

# Metrics that carry a fitted Championship -> Premier League factor.
CALIBRATED_METRICS = {"avg_gf": "gf", "avg_ga": "ga", "avg_shots": "shots", "avg_sot": "shots_ot"}


def _ratio(numerator, denominator):
    """Safe ratio that propagates missingness instead of inventing a value."""
    if numerator is None or denominator is None:
        return np.nan
    try:
        if np.isnan(numerator) or np.isnan(denominator):
            return np.nan
    except TypeError:
        return np.nan
    if denominator == 0:
        return np.nan
    return float(numerator) / float(denominator)


def _mean(values, fallback=np.nan):
    """Mean over the present values, or `fallback` when none are present.

    Replaces the old `series.dropna().mean()`: same semantics, on a numpy slice
    of at most ten elements rather than a pandas Series carved out of the frame.
    """
    if len(values) == 0:
        return fallback
    present = values[~np.isnan(values)]
    return float(present.mean()) if present.size else fallback


# The longest window any rolling feature uses. Only this many of a team's most
# recent matches can affect the result, which is what makes the truncation in
# MatchHistory safe.
LONGEST_ROLLING_WINDOW = history.LONGEST_ROLLING_WINDOW


def _rolling_stats(window: "history.TeamWindow", size: int = 5) -> dict:
    """Rolling form from an already-cut window of a team's matches.

    ## Why this is written the way it is

    Two rewrites ago this derived eleven columns across a club's *entire* history
    in order to produce ten numbers, which was 71% of the feature build. One
    rewrite ago it truncated to the last ten rows first, but still reached that
    truncation through a boolean scan of the frame per fixture per feature —
    which is what left a production retrain sitting on "building feature matrix"
    for fifteen minutes before the first estimator was fitted.

    The cut is now a binary search done once per fixture in `MatchHistory`, and
    this function only reads the resulting slices. See data/history.py for why
    the rows selected are identical rather than approximate.
    """
    if window.played == 0:
        # P5: no history means unknown, not zero. Zero is a meaningful value in
        # every one of these features - a team that "scores 0.0 and concedes 0.0"
        # is a strong (and wrong) signal. NaN lets XGBoost learn a split for
        # missingness.
        unknown = {k: np.nan for k in ROLLING_FEATURES}
        unknown["matches_played"] = 0
        return unknown

    last = slice(-size, None)
    return {
        "avg_gf": _mean(window.gf[last]),
        "avg_ga": _mean(window.ga[last]),
        # Shot quality replaces the old "xg" features, which fell back to goals
        # and so fed the model a second copy of the goals column. Neither data
        # source publishes true expected goals; this is named for what it is.
        "shot_accuracy": _ratio(_mean(window.sot[last]), _mean(window.shots[last])),
        "avg_sot": _mean(window.sot[last]),
        "avg_shots": _mean(window.shots[last]),
        "avg_corners": _mean(window.corners[last]),
        "avg_fouls": _mean(window.fouls[last]),
        "avg_yellows": _mean(window.yellows[last]),
        "form_pts": float(window.pts[last].sum()),
        "cs_rate": _mean(window.cs[last]),
        "btts_rate": _mean(window.btts[-LONGEST_ROLLING_WINDOW:]),
        "over_2_5_rate": _mean(window.over25[-LONGEST_ROLLING_WINDOW:]),
        # Counted over the whole history, not the window - a promoted club's
        # thin evidence is exactly what the sufficiency features report.
        "matches_played": window.played,
    }


def _team_rolling(df: pd.DataFrame, team: str, before_date: str, window: int = 5) -> dict:
    """Rolling form for one team, from matches strictly before `before_date`.

    Kept for callers holding only a frame - it indexes that frame and reads one
    window out of it. Anything looping over fixtures should build a
    `MatchHistory` once and call `_rolling_stats` instead.
    """
    return _rolling_stats(MatchHistory(df).team_window(team, before_date), window)


def _venue_stats(gf: np.ndarray, ga: np.ndarray) -> dict:
    return {"venue_avg_gf": _mean(gf), "venue_avg_ga": _mean(ga)}


def _h2h_stats(total_goals: np.ndarray, home_wins: int) -> dict:
    """Head-to-head record from an already-cut window of meetings."""
    # Two clubs that have never met have no head-to-head record. The old 2.5 /
    # 0.4 defaults were invented league averages presented as this pair's history
    # - exactly the substitution this rebuild removes. Promoted clubs hit this
    # path for most of their fixtures.
    if len(total_goals) == 0:
        return {"h2h_avg_total_goals": np.nan, "h2h_home_win_rate": np.nan}
    return {
        "h2h_avg_total_goals": _mean(total_goals),
        "h2h_home_win_rate": float(home_wins / len(total_goals)),
    }


def _rest_days(window: "history.TeamWindow", before_date: str) -> float:
    """Days since the team's previous match. Meaningful now that dates are ISO."""
    if window.last_date is None:
        return np.nan
    return history.date_ordinal(before_date) - history.date_ordinal(window.last_date)


def _apply_calibration(stats: dict, top_flight_matches: int) -> dict:
    """Translate Championship-earned form toward Premier League scale.

    Weight is 1.0 with no top-flight matches and decays to 0.0 by the tenth,
    so observed evidence progressively replaces the translated estimate.
    """
    weight = prior_weight(top_flight_matches)
    if weight <= 0:
        return stats

    adjusted = dict(stats)
    for feature, metric in CALIBRATED_METRICS.items():
        value = stats.get(feature)
        if value is None:
            continue
        try:
            if np.isnan(value):
                continue
        except TypeError:
            continue
        translated = translate(metric, value)
        adjusted[feature] = weight * translated + (1.0 - weight) * value
    return adjusted


def build_feature_vector(df: pd.DataFrame, home_team: str, away_team: str,
                         before_date: str, strength: "StrengthIndex | None" = None,
                         index: "MatchHistory | None" = None,
                         odds: tuple | None = None) -> dict:
    """Feature vector for one fixture, using only matches before `before_date`.

    `strength` and `index` are optional so a single prediction can build its own;
    pass shared ones when looping, since each is a full pass over history.

    `odds` is the fixture's own pre-match (home, draw, away) decimal prices. It is
    passed in rather than looked up because the two callers get it from different
    places: training reads the stored closing price off the match row, while a
    live prediction has to fetch a price for a fixture that has not been played.
    Absent odds become NaN features, never a neutral prior - see data/odds.py.
    """
    if index is None:
        index = MatchHistory(df)

    # One binary search per club, reused by every window below. Each helper used
    # to re-derive its own cut with a boolean scan of the whole frame.
    home_window = index.team_window(home_team, before_date)
    away_window = index.team_window(away_team, before_date)

    home_stats = _rolling_stats(home_window)
    away_stats = _rolling_stats(away_window)
    home_venue = _venue_stats(*index.venue_window(home_team, "home", before_date))
    away_venue = _venue_stats(*index.venue_window(away_team, "away", before_date))
    h2h = _h2h_stats(*index.h2h_window(home_team, away_team, before_date))

    # P4: a club whose recent form was earned in the Championship has that form
    # translated through the fitted division factors, with the translation losing
    # weight as real top-flight matches accrue.
    home_top = home_window.top_flight
    away_top = away_window.top_flight
    home_stats = _apply_calibration(home_stats, home_top)
    away_stats = _apply_calibration(away_stats, away_top)

    features = {}
    for k, v in home_stats.items():
        features["home_" + k] = v
    for k, v in away_stats.items():
        features["away_" + k] = v

    # Data-sufficiency features: let the model learn to distrust thin evidence
    # rather than treating a promoted club's estimate like observed history.
    features["home_top_flight_matches"] = home_top
    features["away_top_flight_matches"] = away_top
    features["home_is_newly_promoted"] = int(home_top < 10)
    features["away_is_newly_promoted"] = int(away_top < 10)
    features["home_rest_days"] = _rest_days(home_window, before_date)
    features["away_rest_days"] = _rest_days(away_window, before_date)
    features["home_venue_avg_gf"] = home_venue["venue_avg_gf"]
    features["home_venue_avg_ga"] = home_venue["venue_avg_ga"]
    features["away_venue_avg_gf"] = away_venue["venue_avg_gf"]
    features["away_venue_avg_ga"] = away_venue["venue_avg_ga"]
    features["h2h_avg_total_goals"] = h2h["h2h_avg_total_goals"]
    features["h2h_home_win_rate"] = h2h["h2h_home_win_rate"]

    # Composite dominance index, from real shot volume rather than the old
    # "xg" proxy that fell back to goals.
    shots_h = features["home_avg_shots"]
    shots_a = features["away_avg_shots"]
    features["home_dominance_index"] = _ratio(shots_h - shots_a, shots_h + shots_a)

    # P9: opponent-adjusted strength. Everything above this line describes what a
    # club did; only this describes how good it is relative to who it played.
    if strength is None:
        strength = StrengthIndex(df)
    features.update(strength_features(strength, home_team, away_team, before_date))

    # Opponent-adjusted form. The raw averages are kept alongside deliberately:
    # the gap between raw and adjusted is the evidence for whether the adjustment
    # carries signal, and collapsing them would destroy that comparison.
    features["home_adj_avg_gf"] = _ratio(features["home_avg_gf"], features["away_defence"])
    features["away_adj_avg_gf"] = _ratio(features["away_avg_gf"], features["home_defence"])
    features["home_adj_avg_ga"] = _ratio(features["home_avg_ga"], features["away_attack"])
    features["away_adj_avg_ga"] = _ratio(features["away_avg_ga"], features["home_attack"])

    features["home_matches_last_14"] = index.matches_within(home_team, before_date, 14)
    features["away_matches_last_14"] = index.matches_within(away_team, before_date, 14)

    # Pre-match market prices. Unlike everything above these describe the fixture
    # itself rather than the clubs' histories, so they are supplied by the caller.
    features.update(odds_feature_dict(*(odds or (None, None, None))))

    return features
