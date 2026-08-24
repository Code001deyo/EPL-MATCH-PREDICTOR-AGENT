# P4 — Cross-Division Calibration

**Agent:** `feature-engineer`
**Blocks:** P5
**Requires:** P3

## Problem

P3 gives promoted clubs real Championship history. That history is not directly
comparable to Premier League output: a club scoring 1.8 goals per game in the
Championship will not score 1.8 in the Premier League. Feeding E1 statistics in
untranslated replaces one bias (zeros) with another (overrating promoted sides).

## Task

Fit the translation from evidence rather than assuming it.

1. Build the historical panel: for every club promoted in the seasons available,
   pair its final Championship season statistics with its first Premier League
   season statistics. With E1 data from P2 this is a small but real sample.
2. Fit per-statistic shrinkage factors — goals for, goals against, shots, shots on
   target — each with an uncertainty estimate. Keep the model simple; the sample
   is small and an over-parameterised fit will not generalise.
3. Apply the factor as a **prior that decays**: full influence at zero Premier
   League matches played, reaching zero influence at roughly ten. Real observed
   matches must progressively replace the translated ones.
4. Propagate the calibration uncertainty into the prediction confidence, so a
   scoreline resting on translated Championship form is reported as less certain
   than one resting on observed Premier League form.
5. Validate on held-out promoted cohorts.

## Honest-result requirement

Compare calibrated priors against both alternatives on first-ten-match error:

- zeroed features (current behaviour)
- flat league-average promoted-side priors

If calibration does not beat both, report that. A negative result is a real finding
and the fallback (league-average priors) is a legitimate outcome. Do not tune the
factor until it looks good on the validation set you are also reporting.

## Constraint

Only three clubs are promoted per season, so the panel grows slowly. Extending the
window further back brings in less comparable football. State the sample size
alongside any factor you report — a shrinkage factor fitted on nine clubs is an
estimate, not a constant.

## Acceptance criteria

- Fitted factors reported per statistic, each with sample size and uncertainty.
- Held-out comparison against both baselines, with actual numbers.
- Decay behaviour tested: a club's features provably converge on observed data as
  matches accrue.
- Calibration uncertainty is visible in the confidence output, not discarded.
