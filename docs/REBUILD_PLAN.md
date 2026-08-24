# EPL Predictor — Rebuild Plan

Phase index. Each phase has a technical brief in `docs/prompts/` and an owning
agent definition in `.claude/agents/`.

A phase is done when its acceptance criteria are demonstrated with **real output**
— counts, metrics, or a passing regression test — not when the code runs.

---

## Wave 1 — data integrity (complete)

| Phase | Owner | Status |
|---|---|---|
| P0 Dynamic season discovery | data-ingestion-engineer | **Done** |
| P1 Chronological integrity | data-ingestion-engineer | **Done** |
| P2 Dual-source ingestion | data-ingestion-engineer | **Done** — 100% stat coverage on completed seasons |
| P3 Team registry & continuity | data-ingestion-engineer | **Done** |
| P4 Cross-division calibration | feature-engineer | **Done** — 21 promoted club-seasons |
| P5 Feature layer rebuild | feature-engineer | **Done** — synthetic constants removed |
| P6 Retrain & benchmark | model-trainer | **Done** — see baseline below |
| P7 Frontend provenance | frontend-integrator | **Done** |

## Wave 2 — accuracy and presentation (complete)

| Phase | Owner | Status |
|---|---|---|
| P8 Estimator unblock & count loss | model-trainer | **Done** |
| P9 Predictive strength features | feature-engineer | **Done** |
| P10 Backtest & settled accuracy | model-trainer | **Done** — re-run 2026-08-24, results below |
| P11 Dashboard redesign | dashboard-designer | **Done** |

---

## P6/P8 measured baseline — 2026-08-24

The first real training run. Holdout is the **2025-26 season (389 matches)**,
trained on 2280 earlier matches. Reported in full, including where it is weak.

> **Superseded 2026-08-24.** The figures in this section were the first real
> training run and are kept for the diagnosis that follows them. The current
> measured numbers are in `docs/FINALISATION_LOG.md`; where the two disagree,
> the artefact wins. The headline moved to 46.0% / 1.0413, and the "best
> baseline" column below was wrong in an important way — the Poisson baseline
> it compared against was a copy of the constant baseline (see N4 in the log).

| Metric | Model | Best baseline | Verdict |
|---|---|---|---|
| Correct result | **44.7%** | 43.4% (always home) | +1.3pt — marginal |
| Exact score | **10.0%** | — | low but typical |
| Outcome log loss | **1.0611** | 1.0815 (base rate) | beats it, narrowly |
| home_goals MAE | **0.959** | 0.990 (median) | beats it |
| away_goals MAE | **0.874** | 0.789 (median) | **loses** |

Statistic models (MAE, same holdout): shots 3.59/3.42, shots on target
1.86/1.65, corners 2.13/2.09, fouls 2.58/2.75, yellow cards 0.99/1.12.

**Honest reading.** The model is real but weak. A competent football model calls
52–55% of results and reaches ~1.00 log loss; bookmaker closing odds are around
0.98. At 44.7% and 1.061 this clears "predicts nothing" and little else. The
away-goals MAE loss to the median is expected — MAE is minimised by the median
and Premier League away goals are median 1 — but it should not be waved away.

**Diagnosed cause, and what P9 is for.** Every feature is a team's own rolling
average, unadjusted for who it was played against. Six goals against a relegated
side and six against the champions enter the model identically. The model has no
representation of *team strength*, so it cannot know that Chelsea's 1.4 goals per
game were harder-won than Burnley's. That is the single largest gap and it is
what P9 addresses.

---

## Two bugs found while producing that table

Recorded because both produced plausible-looking numbers rather than errors, and
that is the failure mode this project keeps hitting.

**The holdout was nine matches.** `_season_split_index` held out the newest
season, which is the one in progress. Validation ran on 9 games, every one of the
ten statistic models was skipped for having zero validation rows, and the
baseline comparison was noise. Fixed: the holdout must be the most recent season
with at least `MIN_HOLDOUT_MATCHES` (200) matches.

**The estimator was unreachable.** `_make_model()` called `from xgboost import
XGBRegressor` on the hot path, so with that wheel absent every retrain returned
500 and every prediction returned 503 "not trained yet" — a data-independent
failure that looked exactly like an untrained model. Fixed: `models/backend.py`
selects XGBoost or scikit-learn HistGradientBoosting, and names which one it used
in `metrics.json`.

---

## P9 — a leak found by its own acceptance test

The P9 brief required a leakage test. It found two, in code that had already been
written, reviewed and used to produce a full set of headline numbers. Both are
recorded here because neither raised an error — both produced entirely plausible
ratings, and the only thing that exposed them was a test that mutated results and
asserted what must *not* move.

**1. Snapshots were taken before the match but stamped with its date.** A lookup
for a fixture therefore resolved to the state before the *previous* match, so
every rating was one result stale.

**2. League scoring rates were the mean of the whole DataFrame.** This is the
serious one. The multiplicative ratings are defined relative to a league rate, so
taking that rate over all loaded rows made every historical rating depend on
matches that had not yet been played. Appending one future 6-0 shifted the league
mean, which shifted the seeds, which shifted every rating in the past —
information flowing backwards through time.

Fixed by storing post-match state stamped with the match date (so a lookup takes
the last entry strictly earlier, and two fixtures on the same day cannot see each
other), and by seeding league rates from documented constants updated online.

**Consequence for P10.** The walk-forward backtest was run against the leaky
feature set. Its headline of 51.4% across 2,460 matches is therefore not
trustworthy and must be re-run. A backtest is precisely the instrument that
cannot be allowed to run on leaked features, because leakage inflates it and the
inflated number is then used as evidence the model works.

**Re-run 2026-08-24 — and the table had been empty all along.** P10 was marked
Done, but the `backtests` table held **zero rows**: the runner existed and had
never produced a stored result, so the dashboard calibration panel had nothing
to draw and `/model/backtest` answered "No backtest results" indefinitely.

Re-run over 3 completed seasons on the de-leaked feature set: **1,140 matches,
114 walk-forward folds, 53.3% correct result, 9.8% exact score, log loss 0.9937**
against a 43.2% always-home baseline. Per season: 59.5% (2023-24), 52.6%
(2024-25), 47.9% (2025-26).

That 53.3% is *above* the 46.0% season-holdout figure, and that is not evidence
the model improved. The backtest refits before every matchweek, so a late-season
fold has seen that season's earlier rounds; the holdout model never sees the
season it is scored on. Different conditions, kept as separate figures.

Confidence calibration was checked at the same time and came out **good** —
monotonic across six buckets, 36.9% observed in the 0-40% band up to 85.4% in
the 80-100% band. Full table in `docs/FINALISATION_LOG.md`.


---

## Wave 3 — finalisation (2026-08-24)

Deployment, data currency, retrain UX, honest baselines and dashboard
completeness. See `docs/FINALISATION_LOG.md` for the full record, including the
two results the model does not win.
