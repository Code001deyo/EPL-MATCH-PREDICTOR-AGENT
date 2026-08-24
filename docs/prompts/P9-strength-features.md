# P9 — Predictive strength features

**Owner:** feature-engineer
**Depends on:** P5 (feature layer), P8 (count loss, fixed holdout)
**Measured against:** the P8 baseline in `docs/REBUILD_PLAN.md`

---

## The problem

The model calls 44.7% of results against a 43.4% always-home baseline. The cause
is not the estimator and is no longer the data supply — it is that every feature
is **opponent-unadjusted**.

`data/features.py` builds each side's rolling averages over its own last N
matches: goals for, goals against, shots, shot accuracy, corners, form points.
None of them know who the opponent was. Two clubs averaging 1.8 goals per game
are identical to the model even if one played the top six and the other played
the bottom six. Strength of schedule is invisible, so the model is fitting noise
around the league mean — which is precisely why it barely separates from a
constant.

## What to add

### 1. Attack and defence ratings (the core of this phase)

Fit a Dixon-Coles style Poisson strength model over a trailing window of matches:
each club gets an attack rating and a defence rating, plus one league-wide home
advantage term. Expose per fixture:

- `home_attack`, `home_defence`, `away_attack`, `away_defence`
- `home_expected_goals`, `away_expected_goals` — the strength model's own rate
  prediction for this exact fixture

That last pair matters most. It hands the booster a genuinely informative prior
instead of asking it to rediscover league structure from rolling means.

**Fit only on matches before the fixture date.** The ratings are a feature, and a
rating fitted on the full season leaks the result of the match being predicted.
This is the highest-risk leak in the phase — the ratings must be recomputed per
cutoff, or fitted incrementally forward through time. Verify it.

### 2. Opponent-adjusted form

For the existing rolling windows, weight each match by the opponent's defence
rating (for attacking metrics) or attack rating (for defensive metrics). Emit as
new columns; do not overwrite the raw ones — the comparison between raw and
adjusted is evidence for whether this phase worked.

### 3. Elo

A standard Elo rating updated match by match, with `home_elo`, `away_elo` and
`elo_diff`. Cheap, well-understood, and a useful check: if Elo alone beats the
full feature set, the feature set has a problem.

### 4. Rest and congestion

`home_rest_days` / `away_rest_days` exist. Add `matches_last_14_days` per side.

## Acceptance criteria

Report all of these against the P8 table, **including if they get worse**:

1. Correct-result % on the 2025-26 holdout, versus 44.7%.
2. Outcome log loss, versus 1.0611. This is the primary metric — it is the one
   that judges the probabilities rather than just the top pick.
3. Exact-score %, versus 10.0%.
4. Feature importance after retraining: the strength features should rank near
   the top. If they do not, say so — it means they carry no signal here.
5. A leakage test in `tests/`: assert that a fixture's own result cannot change
   the ratings used to predict it.

A phase that moves log loss below ~1.02 has done its job. A phase that moves it
by 0.001 has not, and must be reported as such rather than dressed up.

## Constraints

- `data/features.py` is already near the 200-line convention. Put the strength
  model in `data/strength.py` and re-export.
- Missing stays missing. A club with no history gets NaN ratings, not 1500 Elo
  by default — except where Elo's own definition requires a seed, which must be
  documented at the seed site.
- Promoted clubs' Championship history flows through the P4 calibration factors
  before entering any rating.
