# P7 — Frontend Provenance and Findings

**Agent:** `frontend-integrator`
**Requires:** P2 (provenance data), P6 (metrics) for full content; the API-base
work can start immediately

## Problem

The UI presents every prediction identically, so a scoreline resting on calibrated
Championship priors looks exactly as authoritative as one backed by five seasons of
Premier League history. It also renders blank stat cards when the backend is
unreachable, which is indistinguishable from a season with no results yet.

Separately, `http://localhost:8001` is hardcoded in nine files:

```
pages/Dashboard.jsx      pages/Predict.jsx        pages/Teams.jsx
pages/History.jsx        pages/Analytics.jsx      pages/ModelPage.jsx
components/PredictionCard.jsx  components/TeamStats.jsx  components/HistoryTable.jsx
```

## Task

1. **Centralise the API base** into one module reading an environment variable with
   a local default. Do this first — it is independent of the other phases and
   removes a nine-file edit from every future change.
2. **New backend endpoints** (coordinate shapes with the backend work):
   - data freshness — when each source was last refreshed, per season
   - coverage — how much of each season carries real statistics
   - reconciliation — matched/unmatched counts from P2
   - model metrics — backtest results from P6
3. **Provenance panel** — which source each statistic came from and when it was
   last refreshed.
4. **Promoted-club badge** on predictions resting on calibrated priors rather than
   observed Premier League history, showing how many real matches stand behind it.
5. **Model page** — backtest results, baseline comparison, feature importance.
6. **Explicit states** for every panel: loading, empty, error, stale. A panel that
   cannot reach the backend must say so rather than rendering zeros.

## Polling

Poll `/health/api`, freshness and metrics on a sensible interval. Do not poll the
prediction endpoint. Show the last successful refresh time rather than implying
live data when a request has failed.

## Copy

Write from the supporter's side, not the schema's: "last updated 12 minutes ago",
"promoted this season — based on 3 Premier League matches", "Championship form,
adjusted". Avoid exposing internal terms like calibration factor or provenance flag
in the interface.

## Acceptance criteria

- Zero hardcoded API base URLs remain in `frontend/src/`.
- A prediction for Coventry is visibly distinguishable from one for Arsenal without
  opening the network tab.
- Every panel's loading, empty, error and stale states are verified by hand.
- The dashboard with the backend stopped shows an explicit connection error, not
  blank stat cards.

## Verify

```bash
docker compose up -d
# then confirm in the browser at http://localhost:3000
docker compose stop backend    # confirm the error state renders honestly
```
