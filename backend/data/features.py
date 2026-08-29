"""The match frame, and the training matrix built from it.

The per-fixture feature layer lives in `vector.py` and the point-in-time index
in `history.py`; this module is the two ends around them — reading matches out
of the database, and looping a fixture at a time to assemble the matrix.

The public names from `vector` are re-exported here because `data.features` is
the import path the routers, the backtest and the tests already use, and because
"the feature layer" is one idea to a caller even when it is three files.
"""
from __future__ import annotations

import threading

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.database import MatchResult
from .history import MatchHistory
from .strength import StrengthIndex
from .vector import (           # noqa: F401  (re-exported: this is the barrel)
    CALIBRATED_METRICS,
    LONGEST_ROLLING_WINDOW,
    ROLLING_FEATURES,
    _apply_calibration,
    _h2h_stats,
    _mean,
    _ratio,
    _rest_days,
    _rolling_stats,
    _team_rolling,
    _venue_stats,
    build_feature_vector,
)


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

# The two point-in-time indexes, cached against that same signature.
#
# `build_feature_vector` takes `index` and `strength` precisely so a caller can
# build them once and reuse them, and its docstring says each is a full pass over
# history. The training path does share them across every fixture in the matrix.
# The single-prediction path did not: it passed neither, so each request built a
# fresh MatchHistory and a fresh StrengthIndex over the whole 11,222-row frame to
# answer one fixture.
#
# Profiled on the seed snapshot, that was 90% of a prediction — StrengthIndex
# 0.100s and MatchHistory 0.079s against 0.018s of actual model inference. On the
# deployed instance, with a frame 1.7x larger and a throttled shared core, the
# same shape of work took **10-12 seconds per prediction, warm**.
_INDEX_CACHE: dict = {}
_INDEX_LOCK = threading.Lock()


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
    with _INDEX_LOCK:
        _INDEX_CACHE.clear()


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


def prediction_indexes(db: Session):
    """`(MatchHistory, StrengthIndex)` over the whole frame, built once per dataset.

    Keyed on the same signature as the frame itself, so the two cannot disagree:
    anything that adds or extends a row moves the signature and rebuilds both, and
    `invalidate_match_cache` clears them together for the enrichment case that
    mutates rows without moving it.

    **Only safe for a fixture that has not been played.** Both indexes are built
    over every row in the frame, so they are correct for a caller whose cut-off is
    later than every stored match — a live prediction, where "today" is after the
    last result. A replayed historical fixture is cut off *inside* the frame and
    must keep building its own index from a frame with that fixture removed, which
    is what `routers/predict.py` does. The strictly-before window would exclude the
    fixture's own row anyway; not sharing the index there means that guarantee does
    not rest on the argument being right.
    """
    signature = _data_signature(db)
    cached = _INDEX_CACHE.get("indexes")
    if cached is not None and cached[0] == signature:
        return cached[1], cached[2]
    with _INDEX_LOCK:
        cached = _INDEX_CACHE.get("indexes")
        if cached is not None and cached[0] == signature:
            return cached[1], cached[2]
        frame = load_matches(db)
        index, strength = MatchHistory(frame), StrengthIndex(frame)
        _INDEX_CACHE["indexes"] = (signature, index, strength)
        return index, strength


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


# Columns carried through the matrix as identifiers or targets rather than as
# features. FEATURE_COLS is an explicit allow-list, so training ignores them;
# they are here so the team-strength Poisson baseline and the backtest can be
# fitted and scored on exactly the rows the model trained on.
CARRIED_COLUMNS = [
    "season", "home_team", "away_team", "date", "home_goals", "away_goals",
    "home_shots", "away_shots", "home_shots_ot", "away_shots_ot",
    "home_corners", "away_corners", "home_fouls", "away_fouls",
    "home_yellow_cards", "away_yellow_cards",
]

# How often the training build reports progress. A retrain spends most of its
# time here, and reporting only on entry left the operator watching an
# indeterminate bar that could not distinguish "working" from "wedged".
PROGRESS_EVERY = 250


def build_training_matrix(df: pd.DataFrame, target_division: str = "E0",
                          on_progress=None):
    """Build the training matrix.

    `df` is the full match history - Championship rows included, because a
    promoted club's form is computed from them. Only Premier League rows become
    training *examples* though: the model predicts Premier League scorelines, and
    training on Championship matches would teach it that division's scoring
    patterns as if they were the same competition.

    `on_progress(stage, done, total)` is optional and reports fixtures built.
    """
    if "division" in df.columns:
        targets = df[df["division"].fillna("E0") == target_division]
    else:
        targets = df

    # Each is a single forward pass over history, built once for the whole
    # matrix. Rebuilding either per row would make this O(n^2) for no gain - and
    # every lookup is point-in-time regardless of when the index was built.
    strength = StrengthIndex(df)
    index = MatchHistory(df)

    # Column arrays rather than `targets.iterrows()`, which materialised a pandas
    # Series per fixture purely to read a dozen scalars off it.
    total = len(targets)
    wanted = list(dict.fromkeys(CARRIED_COLUMNS + ["odds_home", "odds_draw", "odds_away"]))
    columns = {
        name: (targets[name].to_numpy(dtype=object) if name in targets.columns
               else np.full(total, np.nan, dtype=object))
        for name in wanted
    }

    records = []
    for i in range(total):
        feats = build_feature_vector(
            df, columns["home_team"][i], columns["away_team"][i], columns["date"][i],
            strength=strength, index=index,
            # The stored closing price for this very fixture. Not leakage: it was
            # fixed before kick-off and encodes nothing about the result.
            odds=(columns["odds_home"][i], columns["odds_draw"][i],
                  columns["odds_away"][i]),
        )
        for name in CARRIED_COLUMNS:
            feats[name] = columns[name][i]
        records.append(feats)
        if on_progress and (i + 1) % PROGRESS_EVERY == 0:
            on_progress("building feature matrix", i + 1, total)

    if on_progress:
        on_progress("building feature matrix", total, total)
    return pd.DataFrame(records)
