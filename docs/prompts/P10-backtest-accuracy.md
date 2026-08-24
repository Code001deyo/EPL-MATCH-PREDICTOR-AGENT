# P10 — Backtest and settled accuracy

**Owner:** model-trainer
**Depends on:** P8

---

## The problem

`/analytics/model/performance` reports accuracy over the `predictions` table —
rows written when somebody clicks Predict in the UI. On a fresh database that is
empty, so the dashboard shows 0% accuracy over 0 predictions and there is no way
to tell an untested model from a bad one.

Worse, the rows that *do* accumulate are self-selected: they are whatever
fixtures a user happened to ask about, mostly upcoming ones that will never be
settled. That is not a measurement of the model.

## What to build

### 1. A backtest runner — `models/backtest.py`

Walk forward through a completed season. For each matchweek:

- Train (or reuse) a model fitted **only** on matches before that matchweek
- Predict every fixture in the matchweek
- Settle each prediction against the real score already in `match_results`

Store results in a `backtests` table: fixture, date, season, matchweek,
predicted and actual home/away goals, predicted and actual outcome, the three
probabilities, and confidence.

Walk-forward is the requirement, not a nicety. Training once on everything and
then "predicting" past fixtures scores the model on its own training data and
will report accuracy far above what it achieves on a real weekend.

### 2. Settlement for live predictions

A `settle_predictions()` pass that fills `actual_home` / `actual_away` on rows in
`predictions` whose fixture has since been played, matching on team names plus
season and matchweek. Run it on startup after ingestion, so accuracy for
user-made predictions accrues on its own.

### 3. Endpoints

- `GET /model/backtest` — headline accuracy, plus a breakdown by season and by
  matchweek, and calibration buckets (in the matches where the model said 60–70%
  home win, how often did the home side actually win?)
- `POST /model/backtest/run` — trigger a run
- Extend `/analytics/model/performance` to report backtested and live-settled
  accuracy as **separate figures**, clearly labelled

Do not merge backtested accuracy with live prediction accuracy into one number.
They measure different things and blending them hides which is which.

## Acceptance criteria

1. A backtest over at least three completed seasons, reporting correct-result %,
   exact-score %, and log loss, with the per-season table shown.
2. Calibration buckets printed. A model whose "70% confident" calls come in at
   45% is miscalibrated, and that must be visible rather than averaged away.
3. Comparison against always-home and base-rate baselines, per season.
4. A test asserting the walk-forward runner never trains on a match at or after
   the fixture it is predicting.

Report the real numbers. If backtested accuracy is materially below the P8
holdout figure, that is the finding — the holdout may be flattering it.
