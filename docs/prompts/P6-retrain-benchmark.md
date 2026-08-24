# P6 — Retrain, Validate, Benchmark

**Agent:** `model-trainer`
**Requires:** P1, P2, P5 — do not start before these land

## Problem

Two defects in `backend/models/ml_model.py`:

**The split is positional.**

```python
split = int(len(X) * 0.8)
X_train, X_val = X[:split], X[split:]
```

This assumes row order is chronological. Before P1 it was not, and even after P1 a
positional cut splits mid-season and mixes seasons across the boundary.

**Confidence measures rounding, not certainty.**

```python
home_conf = 1 - abs(home_lambda - round(home_lambda))
```

A prediction of exactly 2.0 goals reports maximum confidence whether it rests on
five seasons of evidence or on a promoted club with no history at all.

## Task

1. Season-aware split: train on completed seasons, validate on the most recent
   complete season, hold 2026-27 for live evaluation.
2. Walk-forward backtest by matchweek, so each prediction uses only what was known
   before that matchweek — mirroring real prediction conditions.
3. Establish three baselines and record their numbers **before** tuning anything:
   - home-advantage constant (always predict the league-average home/away scoreline)
   - Poisson on rolling goal averages
   - bookmaker closing odds from the P2 odds columns, as an implied-probability
     benchmark for W/D/L
4. Replace the confidence score with one derived from the predictive distribution
   and the data sufficiency features from P5. Then verify it is calibrated.
5. Report MAE on goals, W/D/L accuracy, exact-score rate, and a calibration curve.
6. Keep predictions explainable — `key_drivers` must reflect the real feature
   importance for that prediction.

## Reporting requirement

Report the comparison against all three baselines, including when it is
unflattering. A model that cannot beat Poisson on goal averages has not earned its
complexity, and that is a legitimate finding to surface rather than tune away. Do
not run many configurations and report only the best; report the process.

## Acceptance criteria

- The model beats the Poisson baseline on held-out seasons, or the shortfall is
  reported plainly with a diagnosis.
- Confidence is calibrated: predictions labelled low-confidence are measurably the
  ones the model gets wrong more often. Show the curve.
- Backtest is walk-forward with no access to future matchweeks — asserted by test.
- Metrics are exposed via an endpoint for the P7 model page.

## Verify

```bash
curl -X POST http://localhost:8001/model/retrain
curl -s http://localhost:8001/model/metrics | python -m json.tool
curl -X POST http://localhost:8001/predict \
  -H "Content-Type: application/json" \
  -d '{"home_team":"Arsenal","away_team":"Coventry","matchweek":4,"season":"2026-27"}'
```

The Coventry prediction is the one to inspect — it should carry visibly lower
confidence than a fixture between two long-established clubs.
