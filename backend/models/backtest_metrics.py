"""Aggregation over walk-forward backtest results.

Kept separate from models/backtest.py (which only runs the simulation and
persists rows) so the "what do these numbers mean" logic — per-season table,
calibration buckets, baselines — has its own home and stays readable.
"""
from __future__ import annotations

import numpy as np

OUTCOME_LABELS = {1: "H", 0: "D", -1: "A"}

# Confidence-style buckets over the winning side's own probability, e.g. every
# prediction where the model gave its top pick 60-70% gets bucketed together
# so miscalibration ("70% confident, comes in at 45%") is visible rather than
# averaged into one headline number.
CALIBRATION_EDGES = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 1.01]


def _row_outcome_probs(row: dict):
    return {1: row["home_win_prob"], 0: row["draw_prob"], -1: row["away_win_prob"]}


def _rps(rows: list) -> float:
    """Ranked Probability Score - the field's standard measure, and the one this
    model should be judged on.

    Accuracy is not a proper scoring rule. It rewards a confident guess exactly as
    much as a well-reasoned one, it can be improved by becoming overconfident, and
    it collapses everything the model said about the other two outcomes. It also
    punishes correct behaviour: draws are ~24% of matches and are almost never the
    single most likely result, so any honest forecaster - including the bookmakers,
    who did not make a draw their favourite in a single one of 7,980 matches -
    looks like it "never predicts draws".

    RPS scores the *cumulative* distribution over the ordered outcomes
    (home, draw, away), so being wrong by one step costs less than being wrong by
    two: calling a home win when the match is drawn is penalised less than calling
    a home win when the away side wins. Lower is better.

    Reference points on this league, walk-forward over 6,080 matches:
        0.1955  bookmaker closing line
        0.2014  this model
        0.2316  always predicting the base rates
        0.2380  a uniform 1/3 each
    """
    losses = []
    for r in rows:
        probs = _row_outcome_probs(r)
        # Ordered home -> draw -> away, matching the natural ordering of the
        # result. The order matters: RPS is distance-sensitive, so shuffling these
        # would silently change what the number means.
        forecast = np.cumsum([probs[1], probs[0], probs[-1]])
        actual = np.cumsum([
            1.0 if r["actual_outcome"] == 1 else 0.0,
            1.0 if r["actual_outcome"] == 0 else 0.0,
            1.0 if r["actual_outcome"] == -1 else 0.0,
        ])
        losses.append(float(((forecast - actual) ** 2).sum() / 2.0))
    return float(np.mean(losses)) if losses else float("nan")


def _market_baseline(rows: list) -> dict:
    """How the bookmakers did on these same fixtures.

    Reported beside the model's own figure because a bare accuracy number is
    uninterpretable. 53% reads as a failure next to nothing, and as within about
    a point of the sharpest forecast in the sport next to 54.6%.

    Only fixtures carrying a stored closing price are counted, so the comparison
    is like-for-like on the same matches rather than the model on all of them and
    the market on a convenient subset.
    """
    from data.odds import market_pick

    scored = [
        (market_pick(r.get("odds_home"), r.get("odds_draw"), r.get("odds_away")), r)
        for r in rows
    ]
    scored = [(pick, r) for pick, r in scored if pick is not None]
    if not scored:
        return {}
    correct = sum(1 for pick, r in scored if pick == r["actual_outcome"])
    return {
        "market_matches": len(scored),
        "market_correct_pct": round(correct / len(scored) * 100, 1),
    }


def _log_loss(rows: list) -> float:
    eps = 1e-9
    losses = []
    for r in rows:
        p = _row_outcome_probs(r)[r["actual_outcome"]]
        losses.append(-np.log(np.clip(p, eps, 1)))
    return float(np.mean(losses)) if losses else float("nan")


def _baselines(rows: list) -> dict:
    """Always-home and base-rate (train-set-free — the season's own split,
    since a walk-forward run has no single held-out set to compute a prior
    from) baselines, matched to what ml_model.py reports for the live holdout.
    """
    if not rows:
        return {}
    n = len(rows)
    always_home_correct = sum(1 for r in rows if r["actual_outcome"] == 1) / n
    counts = {1: 0, 0: 0, -1: 0}
    for r in rows:
        counts[r["actual_outcome"]] += 1
    base_rate = {k: v / n for k, v in counts.items()}
    eps = 1e-9
    base_ll = float(np.mean([
        -np.log(np.clip(base_rate[r["actual_outcome"]], eps, 1)) for r in rows
    ]))
    return {
        "always_home_pct": round(always_home_correct * 100, 1),
        "base_rate_log_loss": round(base_ll, 4),
    }


def _score_group(rows: list) -> dict:
    n = len(rows)
    if n == 0:
        return {"matches": 0}
    correct = sum(1 for r in rows if r["predicted_outcome"] == r["actual_outcome"])
    exact = sum(1 for r in rows if r["predicted_home"] == r["actual_home"] and r["predicted_away"] == r["actual_away"])
    out = {
        "matches": n,
        "correct_result_pct": round(correct / n * 100, 1),
        "exact_score_pct": round(exact / n * 100, 1),
        # Primary metric. Listed before log loss and accuracy because it is the
        # one the model is actually tuned against.
        "rps": round(_rps(rows), 4),
        "log_loss": round(_log_loss(rows), 4),
    }
    out.update(_baselines(rows))
    out.update(_market_baseline(rows))
    out["beats_always_home"] = out["correct_result_pct"] > out.get("always_home_pct", -1)
    return out


def _calibration_buckets(rows: list) -> list:
    """For matches where the model's top pick carried probability in [lo, hi),
    how often was that pick actually right? A well-calibrated model's observed
    rate should track the bucket midpoint."""
    buckets = []
    for lo, hi in zip(CALIBRATION_EDGES[:-1], CALIBRATION_EDGES[1:]):
        in_bucket = []
        for r in rows:
            probs = _row_outcome_probs(r)
            top_p = probs[r["predicted_outcome"]]
            if lo <= top_p < hi:
                in_bucket.append(r)
        if not in_bucket:
            continue
        hits = sum(1 for r in in_bucket if r["predicted_outcome"] == r["actual_outcome"])
        buckets.append({
            "confidence_range": f"{int(lo * 100)}-{int(hi * 100)}%",
            "predictions": len(in_bucket),
            "actual_hit_rate_pct": round(hits / len(in_bucket) * 100, 1),
        })
    return buckets


def summarize(rows: list) -> dict:
    if not rows:
        return {
            "matches_scored": 0,
            "detail": "No backtest results. POST /model/backtest/run first.",
        }

    by_season: dict = {}
    for r in rows:
        by_season.setdefault(r["season"], []).append(r)
    season_table = [
        {"season": s, **_score_group(group)}
        for s, group in sorted(by_season.items())
    ]

    by_mw: dict = {}
    for r in rows:
        by_mw.setdefault((r["season"], r["matchweek"]), []).append(r)
    matchweek_table = [
        {"season": s, "matchweek": mw, **_score_group(group)}
        for (s, mw), group in sorted(by_mw.items())
    ]

    return {
        "matches_scored": len(rows),
        "seasons_covered": sorted(by_season.keys()),
        "headline": _score_group(rows),
        "by_season": season_table,
        "by_matchweek": matchweek_table,
        "calibration_buckets": _calibration_buckets(rows),
    }
