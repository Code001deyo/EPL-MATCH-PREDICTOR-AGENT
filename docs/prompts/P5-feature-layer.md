# P5 — Feature Layer Rebuild

**Agent:** `feature-engineer`
**Blocks:** P6
**Requires:** P1, P2, P4

## Problem

`backend/data/features.py` substitutes constants wherever data is absent, so the
model cannot distinguish an unknown from a measurement. Two distinct defects:

**Silent zeros for unknown teams** — `_team_rolling()` returns all features as
`0.0` when a team has no prior matches (`features.py:70`). Zero is a meaningful
value in every one of these features; "unknown" is not zero.

**Constant fallbacks for absent statistics** — listed in the P2 brief. After P2
these columns hold real data, so the fallbacks become dead code that must be
removed rather than left as a silent trap for the next gap.

## Task

1. Delete every fallback constant. Pass `NaN` through — XGBoost handles missing
   values natively and will learn a split direction for them.
2. Remove the possession features entirely. Neither source provides possession and
   a proxy for it would repeat the original mistake.
3. Rebuild the shot-quality features from real shots and shots on target, named for
   what they are. Do not call anything `xg` unless it is genuinely expected goals;
   if a proxy is used, name it `shot_quality_proxy` or similar so no reader mistakes
   it for a measurement.
4. Add data-sufficiency features so the model can learn to distrust thin evidence:
   - `home_matches_played` / `away_matches_played`
   - `is_newly_promoted` per side
   - `division_of_origin` for recent history
5. Add fixture-context features now that P1 makes dates reliable:
   - rest days since previous match per side
   - fixture congestion over a trailing window
6. Recompute rolling windows over division-tagged history with P4 calibration
   applied to Championship rows.
7. Apply the P4 decaying prior in feature assembly.

## Rule

Every feature must add signal the model does not already have. `avg_shots` computed
as `avg_gf * 4.5` is `avg_gf`. If you cannot state what independent information a
feature carries, remove it.

## Acceptance criteria

- No constant fallback remains in `features.py`; grep for the literals `4.5`,
  `2.5`, `50.0`, `11.0`, `1.5` and justify anything still present.
- No feature is an arithmetic restatement of goals.
- A team with no history produces `NaN` features, not zeros — asserted by test.
- Feature importance recomputed and reviewed against football sense; anything
  implausibly dominant is investigated for leakage.
- The file is split by domain if it approaches ~200 lines, per project convention.

## Out of scope

Do not retrain or report model metrics — that is P6. This phase changes what the
model is shown, not how it learns.
