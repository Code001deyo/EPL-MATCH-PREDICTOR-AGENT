"""P10: the walk-forward backtest runner must never train a model on a match
at or after the fixture it is about to predict.

This exercises the pure fold-generation logic in models/backtest.py without
touching the database or the ML backend, so it runs fast and independent of
whether xgboost is installed.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.backtest import _season_matchweek_folds, MIN_TRAIN_ROWS


def _synthetic_meta(n_seasons=3, matches_per_mw=4, mws_per_season=6):
    """A small, deterministic, chronologically-ordered fixture list spanning
    several seasons and matchweeks — enough to exercise every fold without
    the cost of the real ~2660-row history."""
    rows = []
    for s in range(n_seasons):
        season = f"20{20 + s}-{21 + s}"
        for mw in range(1, mws_per_season + 1):
            for m in range(matches_per_mw):
                rows.append({
                    "id": len(rows),
                    "date": None,
                    "season": season,
                    "matchweek": mw,
                    "home_team": f"Team{m}",
                    "away_team": f"Team{m + 1}",
                })
    # Build proper strictly-increasing ISO dates: one calendar day per
    # matchweek, shared by every fixture within that matchweek (as real
    # Premier League matchweeks are), strictly after every earlier matchweek.
    idx = 0
    day_counter = 0
    for s in range(n_seasons):
        for mw in range(1, mws_per_season + 1):
            date = pd.Timestamp("2019-08-01") + pd.Timedelta(days=day_counter)
            for m in range(matches_per_mw):
                rows[idx]["date"] = date.strftime("%Y-%m-%d")
                idx += 1
            day_counter += 7
    return pd.DataFrame(rows)


def test_folds_never_train_on_a_match_at_or_after_its_own_matchweek():
    meta = _synthetic_meta(n_seasons=3, matches_per_mw=4, mws_per_season=6)
    # Small min_train_rows so early matchweeks in later seasons still yield a
    # fold — the synthetic fixture list is much smaller than the real one.
    folds = list(_season_matchweek_folds(meta, min_train_rows=4))
    assert len(folds) > 0, "expected at least one backtestable fold"

    for season, mw, train_idx, predict_idx in folds:
        train_dates = meta.loc[train_idx, "date"]
        predict_dates = meta.loc[predict_idx, "date"]
        max_train_date = train_dates.max()
        min_predict_date = predict_dates.min()

        assert max_train_date < min_predict_date, (
            f"{season} MW{mw}: a training row dated {max_train_date} is not "
            f"strictly before the earliest predicted fixture {min_predict_date}"
        )

        # Stronger, row-by-row form of the same guarantee: no individual
        # training row shares or exceeds the date of any predicted row.
        for pd_date in predict_dates:
            assert (train_dates < pd_date).all()

        # Every predicted row in this fold actually belongs to this matchweek.
        assert (meta.loc[predict_idx, "season"] == season).all()
        assert (meta.loc[predict_idx, "matchweek"] == mw).all()


def test_folds_skip_groups_without_enough_training_history():
    meta = _synthetic_meta(n_seasons=1, matches_per_mw=4, mws_per_season=3)
    # First matchweek of the only season has zero prior matches — must be
    # skipped entirely rather than "trained" on nothing.
    folds = list(_season_matchweek_folds(meta, min_train_rows=1))
    seasons_mws = [(s, mw) for s, mw, _, _ in folds]
    assert (meta["season"].iloc[0], 1) not in seasons_mws


def test_default_min_train_rows_is_not_trivially_small():
    # Guards against a "backtest" that trains on a handful of early-season
    # matches and reports it as a measurement.
    assert MIN_TRAIN_ROWS >= 100
