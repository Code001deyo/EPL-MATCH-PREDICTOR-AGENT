"""Walk-forward backtest runner.

`/analytics/model/performance` reports accuracy over the `predictions` table,
whose rows are self-selected — whatever fixtures a user happened to click
Predict on. This module runs a systematic simulation instead: for every
completed matchweek, refit the estimator on only the matches strictly before
that matchweek's earliest fixture, predict every fixture in it, and score
against the real result already sitting in `match_results`.

Feature computation is NOT walk-forward here because it does not need to be:
`build_training_matrix` already builds every row's features from
`df["date"] < before_date` (see data/features.py), so a row's feature vector
never depends on anything at or after its own kickoff regardless of when the
matrix is built. What must be walk-forward is the *estimator* — fitting once
on the full history and then "predicting" the past scores the model on rows
it trained on. So the full matrix is built once (expensive, ~minutes) and then
sliced by row position per matchweek; only the fit is repeated per step.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from data.features import load_matches, build_training_matrix
from models.backend import make_model, fit, clean_matrix
from models.ml_model import (
    FEATURE_COLS, _poisson_probs, _argmax_outcome, _confidence, most_likely_scoreline,
)
from db.database import Backtest

# A matchweek is only backtested if at least this many earlier matches exist
# to train on. Guards against fitting a model on a handful of early-season
# rows and calling the result a measurement.
MIN_TRAIN_ROWS = 200

# How many recent completed seasons to score by default. P10 requires at least
# three; every additional season costs a full set of per-matchweek refits.
DEFAULT_BACKTEST_SEASONS = 3

# 20 clubs x 38 rounds — used to tell a finished season from the current one.
COMPLETE_SEASON_MATCHES = 380


def _season_matchweek_folds(meta: pd.DataFrame, min_train_rows: int):
    """Yield (season, matchweek, train_idx, predict_idx) per backtestable group.

    `meta` must be in the same chronological order `load_matches` guarantees.
    A group's cutoff is the earliest date among its own fixtures; the training
    set is every row strictly before that date. That is the walk-forward
    invariant this module exists to enforce, and it is pure/testable without
    touching the ML backend — see tests/test_backtest_leakage.py.
    """
    for (season, mw), g in meta.groupby(["season", "matchweek"], sort=False):
        cutoff_date = g["date"].min()
        train_idx = meta.index[meta["date"] < cutoff_date].to_numpy()
        if len(train_idx) < min_train_rows:
            continue
        yield season, mw, train_idx, g.index.to_numpy()


def _build_matrix(db: Session):
    """Full feature matrix + aligned fixture metadata, built exactly once.

    The session's transaction is released as soon as the rows are in memory. A
    walk-forward run refits per matchweek and takes far longer than a single
    retrain, and managed Postgres terminates connections left idle inside a
    transaction - which killed a production retrain outright. Everything after
    this read is pure computation until `_store_results` writes at the end, and
    that write simply begins a fresh transaction.
    """
    df = load_matches(db)
    db.commit()
    e0 = df[df["division"].fillna("E0") == "E0"].reset_index(drop=True)
    feat_df = build_training_matrix(df).reset_index(drop=True)
    if len(e0) != len(feat_df):
        raise RuntimeError(
            f"feature matrix ({len(feat_df)}) misaligned with E0 fixtures ({len(e0)})"
        )
    for col in FEATURE_COLS:
        if col not in feat_df.columns:
            feat_df[col] = np.nan

    meta = e0[["id", "date", "season", "matchweek", "home_team", "away_team",
               "odds_home", "odds_draw", "odds_away"]].copy()
    X = clean_matrix(feat_df[FEATURE_COLS].values)
    y_home = feat_df["home_goals"].values.astype(float)
    y_away = feat_df["away_goals"].values.astype(float)
    return meta, feat_df, X, y_home, y_away


def _as_optional_float(value):
    """pandas NaN -> None, so an absent price is stored as NULL rather than as the
    float nan, which SQLite accepts and every consumer then has to re-check."""
    try:
        if value is None or value != value:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _predict_fold(X, y_home, y_away, feat_df, meta, train_idx, predict_idx):
    home_model = fit(make_model(), X[train_idx], y_home[train_idx])
    away_model = fit(make_model(), X[train_idx], y_away[train_idx])

    rows = []
    for i in predict_idx:
        h_lambda = max(float(home_model.predict(X[i:i + 1])[0]), 0.1)
        a_lambda = max(float(away_model.predict(X[i:i + 1])[0]), 0.1)
        home_p, draw_p, away_p = _poisson_probs(h_lambda, a_lambda)
        # Same decision rule as the live path. If these two ever diverge again the
        # backtest stops measuring the product and starts measuring something the
        # user is never shown, which is how a 48% prediction came to be reported
        # as 53%.
        pred_home, pred_away, _outcome = most_likely_scoreline(h_lambda, a_lambda)
        confidence = _confidence(h_lambda, a_lambda, feat_df.iloc[i].to_dict())
        r = meta.iloc[i]
        rows.append({
            "fixture_id": int(r["id"]),
            "season": r["season"],
            "matchweek": int(r["matchweek"]),
            "date": r["date"],
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "predicted_home": pred_home,
            "predicted_away": pred_away,
            "actual_home": int(y_home[i]),
            "actual_away": int(y_away[i]),
            "home_win_prob": home_p,
            "draw_prob": draw_p,
            "away_win_prob": away_p,
            "confidence": confidence,
            # Carried, never consumed by the model. Lets the summary report what
            # the bookmakers made of the same fixture.
            "odds_home": _as_optional_float(r["odds_home"]),
            "odds_draw": _as_optional_float(r["odds_draw"]),
            "odds_away": _as_optional_float(r["odds_away"]),
            "predicted_outcome": _argmax_outcome(home_p, draw_p, away_p),
            "actual_outcome": _argmax_outcome(
                1.0 if y_home[i] > y_away[i] else 0.0,
                1.0 if y_home[i] == y_away[i] else 0.0,
                1.0 if y_home[i] < y_away[i] else 0.0,
            ),
        })
    return rows


def run_backtest(db: Session, min_train_rows: int = MIN_TRAIN_ROWS,
                 seasons: int | None = DEFAULT_BACKTEST_SEASONS,
                 on_progress=None) -> dict:
    """Run the walk-forward simulation, replace the stored results, and return
    the same summary GET /model/backtest reports.

    `seasons` limits how many of the most recent completed seasons are *scored*.
    Training still uses the entire history before each fold's cutoff — only the
    predicted folds are bounded, because a refit happens per matchweek and
    scoring every season is far slower without changing what the calibration
    buckets tell you.
    """
    meta, feat_df, X, y_home, y_away = _build_matrix(db)

    scored_seasons = _recent_complete_seasons(meta, seasons)
    if scored_seasons is not None:
        print(f"Backtesting seasons: {sorted(scored_seasons)}")

    folds = [
        f for f in _season_matchweek_folds(meta, min_train_rows)
        if scored_seasons is None or f[0] in scored_seasons
    ]

    results = []
    for i, (season, mw, train_idx, predict_idx) in enumerate(folds, 1):
        print(f"Backtesting {season} MW{mw}: {len(train_idx)} train rows, {len(predict_idx)} fixtures")
        if on_progress:
            on_progress(f"{season} MW{mw}", i, len(folds))
        results.extend(_predict_fold(X, y_home, y_away, feat_df, meta, train_idx, predict_idx))

    _store_results(db, results)
    from models.backtest_metrics import summarize
    summary = summarize(results)
    summary["seasons_scored"] = sorted(scored_seasons) if scored_seasons else "all"
    return summary


def _recent_complete_seasons(meta: pd.DataFrame, limit: int | None):
    """The `limit` most recent seasons that actually finished.

    The in-progress season is excluded: it has only a handful of matchweeks, and
    including it would let a partial season dominate the "most recent" slice.
    """
    if limit is None:
        return None
    counts = meta.groupby("season").size()
    complete = [s for s, n in counts.items() if n >= COMPLETE_SEASON_MATCHES]
    return set(sorted(complete)[-limit:]) if complete else None


def _store_results(db: Session, results: list) -> None:
    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.query(Backtest).delete()
    for r in results:
        db.add(Backtest(
            fixture_id=r["fixture_id"], season=r["season"], matchweek=r["matchweek"],
            date=r["date"], home_team=r["home_team"], away_team=r["away_team"],
            predicted_home=r["predicted_home"], predicted_away=r["predicted_away"],
            actual_home=r["actual_home"], actual_away=r["actual_away"],
            home_win_prob=r["home_win_prob"], draw_prob=r["draw_prob"],
            away_win_prob=r["away_win_prob"], confidence=r["confidence"],
            odds_home=r.get("odds_home"), odds_draw=r.get("odds_draw"),
            odds_away=r.get("odds_away"),
            run_at=run_at,
        ))
    db.commit()
