from __future__ import annotations

import pandas as pd
import threading

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session
from db.database import MatchResult
from .calibration import translate, prior_weight
from .strength import StrengthIndex, strength_features, STRENGTH_FEATURES
from .odds import odds_feature_dict

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


# The match frame, cached with the row signature it was built from.
#
# Every prediction rebuilt this: 6,545 ORM rows materialised into dicts and then
# into a DataFrame, measured at 0.48s per request. With ten simultaneous users
# that is roughly five seconds of the total wall clock spent rebuilding an
# identical frame ten times.
#
# The cache key is (row count, max id, max date) rather than a timestamp we
# maintain by hand. Anything that adds, removes or extends the data moves at least
# one of those, and the alternative — remembering to invalidate at every write
# site — is the kind of bookkeeping that works until someone adds an eleventh
# write path. Statistics being *enriched* onto existing rows does not move the
# signature, which is why refresh_live_data below clears the cache explicitly.
_FRAME_CACHE: dict = {}
_FRAME_LOCK = threading.Lock()


def _data_signature(db: Session):
    return db.query(
        func.count(MatchResult.id),
        func.max(MatchResult.id),
        func.max(MatchResult.date),
    ).one()


def invalidate_match_cache():
    """Drop the cached frame. Call after any write that mutates existing rows."""
    with _FRAME_LOCK:
        _FRAME_CACHE.clear()


def load_matches(db: Session) -> pd.DataFrame:
    """All matches in chronological order, cached between requests."""
    signature = _data_signature(db)
    cached = _FRAME_CACHE.get("frame")
    if cached is not None and cached[0] == signature:
        return cached[1]
    with _FRAME_LOCK:
        cached = _FRAME_CACHE.get("frame")
        if cached is not None and cached[0] == signature:
            return cached[1]
        frame = _build_match_frame(db)
        _FRAME_CACHE["frame"] = (signature, frame)
        return frame


def _build_match_frame(db: Session) -> pd.DataFrame:
    # Ordered by ISO date then id, so ties within a day are deterministic.
    # Every window below relies on this frame being in true chronological order.
    rows = db.query(MatchResult).order_by(MatchResult.date, MatchResult.id).all()
    return pd.DataFrame([{
        "id": r.id, "season": r.season, "matchweek": r.matchweek,
        "date": r.date, "division": r.division, "stats_source": r.stats_source,
        "home_team": r.home_team, "away_team": r.away_team,
        "home_goals": r.home_goals, "away_goals": r.away_goals,
        "home_xg": r.home_xg, "away_xg": r.away_xg,
        "odds_home": r.odds_home, "odds_draw": r.odds_draw, "odds_away": r.odds_away,
        "home_shots_ot": r.home_shots_ot, "away_shots_ot": r.away_shots_ot,
        "home_shots": r.home_shots, "away_shots": r.away_shots,
        "home_corners": r.home_corners, "away_corners": r.away_corners,
        "home_fouls": r.home_fouls, "away_fouls": r.away_fouls,
        "home_yellow_cards": r.home_yellow_cards, "away_yellow_cards": r.away_yellow_cards,
    } for r in rows])


def _safe_mean(series, fallback=np.nan):
    v = series.dropna()
    return float(v.mean()) if len(v) > 0 else fallback


def _top_flight_matches(df: pd.DataFrame, team: str, before_date: str) -> int:
    """Premier League matches played before this date. Drives calibration decay."""
    if "division" not in df.columns:
        return 0
    played = df[
        ((df["home_team"] == team) | (df["away_team"] == team))
        & (df["date"] < before_date)
        & (df["division"].fillna("E0") == "E0")
    ]
    return int(len(played))


# The longest window any rolling feature uses. Only this many of a team's most
# recent matches can affect the result, which is what makes the truncation below
# safe.
LONGEST_ROLLING_WINDOW = 10


def _team_rolling(df: pd.DataFrame, team: str, before_date: str, window: int = 5) -> dict:
    """Rolling form for one team, from matches strictly before `before_date`.

    ## Why this is written the way it is

    The obvious version - and the one this replaced - derived eleven columns
    (goals for, against, shots, points, clean sheets, ...) across the team's
    *entire* history, concatenated home and away, sorted, and then read
    `.tail(5)` and `.tail(10)` off the end. It did work proportional to a club's
    whole past in order to produce ten numbers.

    That was 71% of the total feature-build time under cProfile, and it is why
    extending the history from seven seasons to twenty-one turned a retrain into
    something that did not finish: the cost is quadratic in the size of the
    database, because every fixture pays for every earlier fixture.

    Only the last `LONGEST_ROLLING_WINDOW` matches can reach any output, so each
    side is truncated to that many *first* and the derived columns are computed on
    at most twenty rows. Results are identical, not approximate:

      - the last ten of the merged sequence must come from the last ten of each
        side, since merging cannot promote an eleventh-from-last row past ten
        later ones;
      - `sort_values` is stable and the concat order is unchanged, so rows sharing
        a date keep the same relative order they had before;
      - `matches_played` still counts the full history, which is cheap because it
        is a length rather than a transformation.
    """
    keep = max(window, LONGEST_ROLLING_WINDOW)

    home_all = df[(df["home_team"] == team) & (df["date"] < before_date)]
    away_all = df[(df["away_team"] == team) & (df["date"] < before_date)]

    # Counted before truncation - this one genuinely needs the whole history.
    total_matches = int(len(home_all) + len(away_all))

    home = home_all.tail(keep).copy()
    away = away_all.tail(keep).copy()

    def _derive(frame, gf_col, ga_col, sot_col, shots_col, corners_col,
                fouls_col, yellows_col):
        """Attach the derived columns for one venue's rows.

        Points are computed with np.where rather than `.apply(lambda ...)`, which
        called a Python function once per row and cost 10 of the 100 seconds in
        the profile on its own.
        """
        gf = frame[gf_col]
        ga = frame[ga_col]
        frame["gf"] = gf
        frame["ga"] = ga
        frame["sot"] = frame[sot_col]
        frame["shots"] = frame[shots_col]
        frame["corners"] = frame[corners_col]
        frame["fouls"] = frame[fouls_col]
        frame["yellows"] = frame[yellows_col]
        frame["pts"] = np.where(gf > ga, 3, np.where(gf == ga, 1, 0))
        frame["cs"] = (ga == 0).astype(int)
        frame["btts"] = ((frame["home_goals"] > 0) & (frame["away_goals"] > 0)).astype(int)
        frame["over25"] = ((frame["home_goals"] + frame["away_goals"]) > 2).astype(int)
        return frame

    home = _derive(home, "home_goals", "away_goals", "home_shots_ot", "home_shots",
                   "home_corners", "home_fouls", "home_yellow_cards")
    away = _derive(away, "away_goals", "home_goals", "away_shots_ot", "away_shots",
                   "away_corners", "away_fouls", "away_yellow_cards")

    cols = ["date", "gf", "ga", "sot", "shots", "corners", "fouls", "yellows", "pts", "cs", "btts", "over25"]
    combined = pd.concat([home[cols], away[cols]]).sort_values("date", kind="stable")

    last5 = combined.tail(window)
    last10 = combined.tail(10)

    # P5: no history means unknown, not zero. Zero is a meaningful value in every
    # one of these features - a team that "scores 0.0 and concedes 0.0" is a
    # strong (and wrong) signal. NaN lets XGBoost learn a split for missingness.
    if len(last5) == 0:
        unknown = {k: np.nan for k in ROLLING_FEATURES}
        unknown["matches_played"] = 0
        unknown["form_pts"] = np.nan
        return unknown

    return {
        "avg_gf": _safe_mean(last5["gf"], fallback=np.nan),
        "avg_ga": _safe_mean(last5["ga"], fallback=np.nan),
        # Shot quality replaces the old "xg" features, which fell back to goals
        # and so fed the model a second copy of the goals column. Neither data
        # source publishes true expected goals; this is named for what it is.
        "shot_accuracy": _ratio(_safe_mean(last5["sot"], fallback=np.nan),
                                _safe_mean(last5["shots"], fallback=np.nan)),
        "avg_sot": _safe_mean(last5["sot"], fallback=np.nan),
        "avg_shots": _safe_mean(last5["shots"], fallback=np.nan),
        "avg_corners": _safe_mean(last5["corners"], fallback=np.nan),
        "avg_fouls": _safe_mean(last5["fouls"], fallback=np.nan),
        "avg_yellows": _safe_mean(last5["yellows"], fallback=np.nan),
        "form_pts": float(last5["pts"].sum()),
        "cs_rate": _safe_mean(last5["cs"], fallback=np.nan),
        "btts_rate": _safe_mean(last10["btts"], fallback=np.nan),
        "over_2_5_rate": _safe_mean(last10["over25"], fallback=np.nan),
        "matches_played": total_matches,
    }


def _venue_split(df: pd.DataFrame, team: str, venue: str, before_date: str, window: int = 5) -> dict:
    if venue == "home":
        matches = df[(df["home_team"] == team) & (df["date"] < before_date)].tail(window)
        gf = _safe_mean(matches["home_goals"]) if len(matches) else np.nan
        ga = _safe_mean(matches["away_goals"]) if len(matches) else np.nan
    else:
        matches = df[(df["away_team"] == team) & (df["date"] < before_date)].tail(window)
        gf = _safe_mean(matches["away_goals"]) if len(matches) else np.nan
        ga = _safe_mean(matches["home_goals"]) if len(matches) else np.nan
    return {"venue_avg_gf": gf, "venue_avg_ga": ga}


def _h2h(df: pd.DataFrame, home_team: str, away_team: str, before_date: str, window: int = 5) -> dict:
    h2h = df[
        (((df["home_team"] == home_team) & (df["away_team"] == away_team)) |
         ((df["home_team"] == away_team) & (df["away_team"] == home_team))) &
        (df["date"] < before_date)
    ].tail(window)

    # Two clubs that have never met have no head-to-head record. The old 2.5 /
    # 0.4 defaults were invented league averages presented as this pair's history
    # — exactly the substitution this rebuild removes. Promoted clubs hit this
    # path for most of their fixtures.
    if len(h2h) == 0:
        return {"h2h_avg_total_goals": np.nan, "h2h_home_win_rate": np.nan}

    total_goals = (h2h["home_goals"] + h2h["away_goals"]).mean()
    home_wins = ((h2h["home_team"] == home_team) & (h2h["home_goals"] > h2h["away_goals"])).sum()
    home_wins += ((h2h["away_team"] == home_team) & (h2h["away_goals"] > h2h["home_goals"])).sum()
    return {
        "h2h_avg_total_goals": float(total_goals),
        "h2h_home_win_rate": float(home_wins / len(h2h)),
    }


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


def _rest_days(df: pd.DataFrame, team: str, before_date: str) -> float:
    """Days since the team's previous match. Meaningful now that dates are ISO."""
    played = df[
        ((df["home_team"] == team) | (df["away_team"] == team))
        & (df["date"] < before_date)
    ]
    if played.empty:
        return np.nan
    last = played["date"].max()
    try:
        return float((pd.to_datetime(before_date) - pd.to_datetime(last)).days)
    except Exception:
        return np.nan


def _matches_in_window(df: pd.DataFrame, team: str, before_date: str, days: int) -> float:
    """Fixture congestion: matches played in the `days` before this one."""
    try:
        cutoff = (pd.to_datetime(before_date) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    except Exception:
        return np.nan
    played = df[
        ((df["home_team"] == team) | (df["away_team"] == team))
        & (df["date"] < before_date)
        & (df["date"] >= cutoff)
    ]
    return float(len(played))


class TeamIndex:
    """Per-team views of the match history.

    Every window helper below filters the frame it is given by team and then by
    date. Handing each one the whole history meant roughly a dozen full-frame
    boolean scans per fixture, and ~32,000 across a full training build — which
    measured as 273 of the 321 seconds a retrain took, i.e. 85% of it.

    The rows a team-scoped helper can possibly use are exactly the rows that
    team appears in, so they are grouped once here. Row order is preserved (the
    helpers rely on chronological order for `.tail(window)`) and the helpers
    still apply their own team and date filters, so results are unchanged — this
    only removes work that could never have matched.
    """

    def __init__(self, df: pd.DataFrame):
        self._df = df
        self._by_team: dict[str, pd.DataFrame] = {}
        if len(df) == 0:
            return
        teams = set(df["home_team"].dropna()) | set(df["away_team"].dropna())
        for team in teams:
            self._by_team[team] = df[
                (df["home_team"] == team) | (df["away_team"] == team)
            ]

    def team(self, name: str) -> pd.DataFrame:
        """This team's matches, in the frame's original chronological order."""
        sub = self._by_team.get(name)
        return self._df.iloc[0:0] if sub is None else sub


def build_feature_vector(df: pd.DataFrame, home_team: str, away_team: str,
                         before_date: str, strength: "StrengthIndex | None" = None,
                         index: "TeamIndex | None" = None,
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
        index = TeamIndex(df)
    home_df = index.team(home_team)
    away_df = index.team(away_team)

    home_stats = _team_rolling(home_df, home_team, before_date)
    away_stats = _team_rolling(away_df, away_team, before_date)
    home_venue = _venue_split(home_df, home_team, "home", before_date)
    away_venue = _venue_split(away_df, away_team, "away", before_date)
    # home_df contains every match home_team played, a superset of the pair's
    # meetings, so the h2h filter still selects exactly the same rows.
    h2h = _h2h(home_df, home_team, away_team, before_date)

    # P4: a club whose recent form was earned in the Championship has that form
    # translated through the fitted division factors, with the translation losing
    # weight as real top-flight matches accrue.
    home_top = _top_flight_matches(home_df, home_team, before_date)
    away_top = _top_flight_matches(away_df, away_team, before_date)
    home_stats = _apply_calibration(home_stats, home_top)
    away_stats = _apply_calibration(away_stats, away_top)

    features = {}
    for k, v in home_stats.items():
        features[f"home_{k}"] = v
    for k, v in away_stats.items():
        features[f"away_{k}"] = v

    # Data-sufficiency features: let the model learn to distrust thin evidence
    # rather than treating a promoted club's estimate like observed history.
    features["home_top_flight_matches"] = home_top
    features["away_top_flight_matches"] = away_top
    features["home_is_newly_promoted"] = int(home_top < 10)
    features["away_is_newly_promoted"] = int(away_top < 10)
    features["home_rest_days"] = _rest_days(home_df, home_team, before_date)
    features["away_rest_days"] = _rest_days(away_df, away_team, before_date)
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

    features["home_matches_last_14"] = _matches_in_window(home_df, home_team, before_date, 14)
    features["away_matches_last_14"] = _matches_in_window(away_df, away_team, before_date, 14)

    # Pre-match market prices. Unlike everything above these describe the fixture
    # itself rather than the clubs' histories, so they are supplied by the caller.
    features.update(odds_feature_dict(*(odds or (None, None, None))))

    return features


def build_training_matrix(df: pd.DataFrame, target_division: str = "E0"):
    """Build the training matrix.

    `df` is the full match history — Championship rows included, because a
    promoted club's form is computed from them. Only Premier League rows become
    training *examples* though: the model predicts Premier League scorelines, and
    training on Championship matches would teach it that division's scoring
    patterns as if they were the same competition.
    """
    if "division" in df.columns:
        targets = df[df["division"].fillna("E0") == target_division]
    else:
        targets = df

    # Built once for the whole matrix. It is a single forward pass over history,
    # so rebuilding it per row would make this O(n^2) for no gain — and every
    # lookup is point-in-time regardless of when the index was constructed.
    strength = StrengthIndex(df)
    # Same reasoning as StrengthIndex: built once for the whole matrix.
    index = TeamIndex(df)

    records = []
    for _, row in targets.iterrows():
        feats = build_feature_vector(
            df, row["home_team"], row["away_team"], row["date"],
            strength=strength, index=index,
            # The stored closing price for this very fixture. Not leakage: it was
            # fixed before kick-off and encodes nothing about the result.
            odds=(row.get("odds_home"), row.get("odds_draw"), row.get("odds_away")),
        )
        feats["season"] = row.get("season")
        # Identifiers, not features — FEATURE_COLS is an explicit allow-list, so
        # these are ignored by training. They are carried so the team-strength
        # Poisson baseline can be fitted on the same rows the model trains on.
        feats["home_team"] = row["home_team"]
        feats["away_team"] = row["away_team"]
        feats["date"] = row["date"]
        feats["home_goals"] = row["home_goals"]
        feats["away_goals"] = row["away_goals"]
        # Extended stat targets — use NaN if column missing/null
        for col in ["home_shots", "away_shots", "home_shots_ot", "away_shots_ot",
                    "home_corners", "away_corners",
                    "home_fouls", "away_fouls", "home_yellow_cards", "away_yellow_cards"]:
            feats[col] = row.get(col, np.nan)
        records.append(feats)
    return pd.DataFrame(records)
