# EPL Score Predictor — Project Guide

Predicts English Premier League scorelines from historical match statistics.
FastAPI + XGBoost + SQLite backend, React + Recharts frontend, Docker Compose.

Repo: `Code001deyo/EPL-MATCH-PREDICTOR-AGENT`

---

## Current state (read this first)

Wave 1 and Wave 2 are complete. A finalisation pass on 2026-08-24 then found that
several phases marked Done did not hold up against the running system — most
importantly P10, whose `backtests` table held zero rows. Read
`docs/FINALISATION_LOG.md` first: it records what was actually measured, and
corrects figures in `docs/REBUILD_PLAN.md` that the artefacts disagree with.

| | |
|---|---|
| P0 Dynamic season discovery | **Done** |
| P1 Chronological integrity | **Done** — ISO dates, reseed forced on legacy rows |
| P2 Dual-source ingestion | **Done** — football-data.co.uk adapter + reconciliation |
| P3 Team registry & continuity | **Done** — Championship backfill for promoted clubs |
| P4 Cross-division calibration | **Done** — factors fitted on 21 promoted club-seasons |
| P5 Feature layer rebuild | **Done** — synthetic constants removed |
| P6 Retrain & benchmark | **Done** — first real metrics recorded |
| P7 Frontend provenance | **Done** |
| P8 Estimator unblock & count loss | **Done** — pluggable backend, Poisson objective |
| P9 Strength ratings | **Done** — attack/defence/Elo, leak-tested |
| P10 Backtest & settled accuracy | **Done** — 1,140 matches over 3 seasons, 53.3% correct |
| P11 Dashboard redesign | **Done** — honest empty states, no fabricated zeros |
| N1-N7 Finalisation | **Done** — see `docs/FINALISATION_LOG.md` |

Verified: `docker exec epl-predictor-backend-1 python -m pytest tests/ -q`.
(`test_api.py` needs httpx, so run the suite in the container.)

Phases were **strictly sequential**: the model must not be retrained on
mis-ordered history or synthetic constants, which is why P6 came last.

---

## The three facts that shape every decision here

**1. Two thirds of the feature vector is currently synthetic.**
`db/database.py` has columns for xG, shots, shots on target, possession, corners,
fouls and cards. `data/ingestion.py` writes `None` to all of them, because the
PulseLive `/fixtures` endpoint does not return them. `data/features.py` then
substitutes constants (`avg_shots` = `avg_gf * 4.5`, `avg_poss` = `50.0`,
`avg_fouls` = `11.0`) and falls `avg_xgf` back to `avg_gf`. The model sees goals
twice under different names and believes it has 30+ features.

**2. Dates are lexicographic strings, so history is mis-ordered.**
Dates are stored `DD/MM/YYYY` and every rolling window filters with
`df["date"] < before_date`. String comparison sorts by day-of-month first.
Fixing this (P1) requires a one-time wipe of the `db_data` volume.

**3. A club is a permanent entity, not a member of this season's league.**
Relegated clubs keep their full history for when they return. Promoted clubs
arrive with real Championship history, translated through a fitted calibration
factor — never zeroed, never invented.

---

## Data sources

**PulseLive** — `https://footballapi.pulselive.com/football`
Authoritative for fixtures, schedule, gameweek and live status. Requires browser
headers or it rejects the request:

```python
{"Origin": "https://www.premierleague.com",
 "Referer": "https://www.premierleague.com/",
 "User-Agent": "Mozilla/5.0"}
```

Season ids are discovered at runtime from `/competitions/1/compseasons` — never
hardcode them. `FALLBACK_SEASON_IDS` in `data/ingestion.py` is an offline
last resort only; do not add new seasons to it.

**football-data.co.uk** — per-match statistics for E0 (Premier) and E1
(Championship): `HS/AS`, `HST/AST`, `HC/AC`, `HF/AF`, `HY/AY`, `HR/AR`, plus
closing odds `B365H/D/A`. This is the source the schema was designed around.

**Neither source provides possession or true xG.** Possession is dropped. Any
xG-named feature must be an explicitly labelled shot-based proxy — never a copy
of the goals column.

---

## Conventions

- **File length** — split files approaching ~200 lines by domain and re-export
  through a barrel, unless there is no natural seam.
- **No hardcoded league membership** — seasons, clubs and divisions are all
  discovered or stored, never pinned in source.
- **Missing means missing** — pass `NaN` to XGBoost, which handles it natively.
  Never substitute a constant for an absent measurement; a fabricated number is
  worse than an honest gap because it silently becomes training signal.
- **No data leakage** — every feature for a fixture must derive only from
  matches played strictly before that fixture's kickoff.
- **Provenance travels with the data** — every stored statistic records which
  source produced it, so the frontend can report it.
- **Reconciliation failures are reported, never absorbed** — an unmatched row is
  logged and counted, not silently defaulted.
- **A baseline the model loses to is reported** — `metrics.json` carries a
  `lost_to` list per target. The Poisson baseline was once literally a copy of
  the constant baseline, and the median was omitted from the verdict flags, so
  the metrics block could only ever report wins.

---

## Layout

```
backend/
  main.py               FastAPI app, /health, /health/ready, /data/*
  lifecycle.py          Background startup ingestion + periodic refresh
  jobs.py               Single-flight background jobs (retrain, backtest)
  data/ingestion.py     Season discovery + PulseLive fetch + DB seed
  data/features.py      Rolling windows, venue splits, h2h, feature vector
  models/ml_model.py    XGBoost train/predict, Poisson W/D/L, confidence
  db/database.py        SQLAlchemy models + lightweight migrations
  routers/              predict, teams, results, analytics
frontend/src/
  pages/                Dashboard, Predict, Teams, History, Analytics, Model
  components/           PredictionCard, TeamStats, HistoryTable, ui/
docs/
  FINALISATION_LOG.md   What was measured on 2026-08-24, and what it corrected
  REBUILD_PLAN.md       Phase index
  prompts/P*.md         Per-phase technical briefs
.claude/agents/         Specialist agent definitions
```

---

## Running it

```bash
docker compose up -d                            # app on :3000
curl http://localhost:3000/api/health           # liveness
curl http://localhost:3000/api/health/ready     # 503 until seeding finishes
curl http://localhost:3000/api/health/api       # confirms PulseLive reachable
curl -X POST http://localhost:3000/api/model/retrain   # 202 + job_id
```

**The backend port is not published.** The browser reaches the API same-origin at
`/api`, proxied by the frontend's nginx to `backend:8000`. Uncomment the `ports`
block in `docker-compose.yml` to hit it directly on :8001 for debugging.

Seeding runs on a background thread, so uvicorn answers `/health` within seconds
of boot; `/health/ready` returns 503 with the current phase until the seed
finishes (measured: 16s to live, 59s to ready on a wiped volume).

Retraining is a background job — `POST /model/retrain` returns 202 with a
`job_id`, and `GET /model/jobs/{job_id}` reports progress. It used to be a
synchronous request that outlived the browser's timeout, so a successful
retrain was reported to the user as a failure.

The backend image build downloads a 297 MB xgboost wheel. `backend/Dockerfile`
uses a BuildKit pip cache mount so an interrupted build resumes instead of
restarting the download — do not reintroduce `--no-cache-dir`.

The frontend API base lives in one place, `frontend/src/config.js`, reading
`REACT_APP_API_BASE` with a default of `/api`. CRA inlines it at build time, so
changing it means rebuilding the image, not restarting it.

---

## Verification

```bash
cd backend && pytest tests/ -v
```

A phase is not done when the code runs. It is done when its brief's acceptance
criteria are demonstrated with real output — counts, metrics, or a passing
regression test. Report what actually happened, including what failed.
