# Finalisation pass — 2026-08-24

Work log for the pass that took the project from "all phases marked Done" to a
system that boots, refreshes, retrains and reports honestly.

Every number below was measured against the running stack, not copied from a
previous document. Where a figure disagrees with `REBUILD_PLAN.md`, the
artefact won and the plan was corrected.

Roles applied: `platform-network-engineer` (N1), `data-ingestion-engineer` (N2),
`model-trainer` + `frontend-integrator` (N3, N4), `dashboard-designer` (N5),
`verification-analyst` (N7). Definitions in `.claude/agents/`.

---

## Starting position

The phase table claimed P0–P11 complete. Probing the live containers found:

| Claim | Reality |
|---|---|
| P10 backtest **Done** | `backtests` table held **0 rows** |
| Model benchmarked against Poisson | `poisson_mae` was assigned `constant_mae` |
| Metrics show the model winning | Median baseline beat it on away goals, and was excluded from the flags |
| Upcoming fixtures broken | Backend served **371** fixtures; the dashboard had no panel for them |
| `/data/refresh` freshens data | It **destroyed** the season's statistics on every call |

The recurring failure mode is not code that errors — it is code that produces
plausible numbers. That framing drove what got tested.

---

## N1 — Network and container correctness

**Changed:** `frontend/nginx.conf`, `frontend/Dockerfile`, `backend/Dockerfile`,
`docker-compose.yml`, `backend/main.py`, new `backend/lifecycle.py`.

- Added an `/api` reverse proxy to nginx and built the bundle with
  `REACT_APP_API_BASE=/api`. The app is now same-origin, so it works from any
  machine that can reach the frontend — previously the compile-time
  `http://localhost:8001` meant only a browser on the Docker host could use it,
  and only because CORS was `["*"]`. Backend port 8001 is no longer published.
- Startup ingestion moved off the synchronous `on_event("startup")` hook onto a
  background thread. Uvicorn used to serve nothing until the whole seed
  finished; there was no way to ask a booting container what it was doing.
- Split liveness from readiness: `/health` is unconditional, `/health/ready`
  returns 503 with the current phase until seeding completes.
- Real healthchecks on both services; frontend now waits on
  `condition: service_healthy` rather than mere container start.
- `npm install` → `npm ci` with the lockfile copied. This immediately caught
  real drift: the committed `package-lock.json` was out of sync with
  `package.json` (missing `yaml@2.9.0`), so every previous image shipped a tree
  nobody had tested. Lockfile regenerated.
- `/health/api` no longer probes the hardcoded `compSeasons=719` (2024-25); it
  uses the current season id, so a green badge means the season in use resolves.

**A bug the healthcheck caught in itself.** The first frontend healthcheck used
`wget http://localhost/`. Busybox resolves `localhost` to `::1` first, and nginx
was only listening on IPv4, so the check failed 77 times in a row while the site
served perfectly. Fixed by adding `listen [::]:80` and probing `127.0.0.1`.
Worth recording because "the page loads" would have hidden it indefinitely — it
was visible only because the container reported itself unhealthy.

**Measured:** cold boot on a wiped volume — backend answering `/health` in
**16s**; full seed complete at **59s** with **zero** recorded errors. Both
containers report `healthy`. Bundle verified to contain no `localhost:8001`.

## N2 — Data currency and the destructive refresh

**Changed:** `backend/data/ingestion.py`, `backend/routers/teams.py`,
`backend/lifecycle.py`.

- `refresh_current_season` now writes `division` and `stats_source`. It
  previously omitted both, so each refresh downgraded the live season to
  NULL provenance and dropped it out of coverage reporting.
- `POST /data/refresh` runs refresh → re-enrich → settle as **one unit**
  (`lifecycle.refresh_live_data`). Calling `refresh_current_season` alone
  deletes the season's rows and re-inserts them from PulseLive, which carries
  goals but no shot data — so the endpoint silently destroyed the
  football-data.co.uk statistics while reporting `{"status": "refreshed"}`.
  It was safe at boot only because enrichment happened to run afterwards.
- `seed_database` compares stored counts against a full 380-fixture campaign
  instead of treating "has ≥1 row" as complete, so a run interrupted part-way
  is now re-fetched rather than left permanently short. The in-progress season
  is exempt — it is legitimately short.
- Added a background refresh loop (`REFRESH_INTERVAL_HOURS`, default 6). Data
  was previously only as fresh as the last container restart.
- `/data/freshness.last_refreshed` reports the real refresh time; it used to
  report process start.

**Measured, after `down -v` and a clean re-seed:**

```
2019-20 E0  380  100.0%     2024-25 E1   90  100.0%
2020-21 E0  380  100.0%     2025-26 E0  380  100.0%
2021-22 E0  380  100.0%     2025-26 E1   90  100.0%
2022-23 E0  380  100.0%     2026-27 E0    9    0.0%
2023-24 E0  380  100.0%
2024-25 E0  380  100.0%     TOTAL 2849 matches, 2840 with statistics (99.7%)
```

The current season (2026-27) has 9 played matches and **no** statistics:
football-data.co.uk has not published its file yet. That is left honestly
NULL and passed to the model as missing, not filled with a default.

**Destructive-refresh regression, run twice in succession:**

| | 2026-27 rows | with `division` | with `stats_source` |
|---|---|---|---|
| before | 9 | 9 | 9 |
| after refresh #1 | 9 | 9 | 9 |
| after refresh #2 | 9 | 9 | 9 |

Under the old code both provenance columns would have gone to 0 on the first call.

## N3 — Async retrain

**Changed:** new `backend/jobs.py`, `backend/routers/model.py`,
`backend/models/ml_model.py`, `backend/data/features.py`, new
`frontend/src/components/model/RetrainPanel.jsx`.

- `POST /model/retrain` returns **202 with a job id immediately**; training runs
  on a worker thread. `GET /model/jobs/{id}` reports state, stage and
  completed/total models.
- Single-flight per job kind. Two retrains had been observed running
  concurrently, interleaved in the container log, both writing the same `.pkl`
  files; a second request now joins the run in flight.
- `routers/model.py` returned `{"error": ...}` with **HTTP 200** when there was
  too little data, so axios resolved and the UI took its success path. Now 409.
- The UI polls, shows the stage and elapsed time, and re-attaches to a job
  already running after a reload.

**Measured:** POST returns in **0.23s**. Full retrain **321s**, of which
**273s (85%)** was `build_training_matrix` — every window helper rescanned the
full 2,849-row frame, ~32,000 full-frame boolean scans per build.

Added `TeamIndex` (`data/features.py`): the rows a team-scoped helper can
possibly use are exactly that team's matches, so they are grouped once and each
helper gets a frame ~14× smaller. Row order is preserved because the helpers
rely on it for `.tail(window)`, and they still apply their own filters — the
change only removes work that could never have matched.

| | before | after |
|---|---|---|
| feature matrix | 273s | 185s (−32%) |
| full retrain | 321s | **252s** (−21%) |

Worth stating plainly: 321s exceeded Chrome's ~300s idle-connection limit. That
is why a retrain which had in fact succeeded was reported to the user as
"Retrain failed." The async job fixes the symptom; the speedup is secondary and
the remaining cost is the per-row Python loop itself, not the scanning.

## N4 — Honest metrics, and the backtest that never ran

**Changed:** `backend/models/ml_model.py`, `backend/models/backtest.py`,
`backend/routers/model.py`.

**The Poisson baseline was fake.** `ml_model.py` assigned
`poisson_mae = constant_mae`, so `"beats_poisson": true` meant only "beats the
training mean" — a baseline no model can fail. Replaced with a real
team-strength Poisson (attack × defence × home advantage, rates fitted on the
training rows only), scored on both MAE and W/D/L.

**The unflattering baseline was hidden.** The median was computed but excluded
from the verdict flags. Every baseline now gets a flag, plus a `lost_to` list.

**Measured on the 2025-26 holdout (389 matches, 55 features):**

| | model | team-strength Poisson | always-home / base rate |
|---|---|---|---|
| correct result | 46.0% | **47.3%** | 43.4% |
| log loss | **1.0413** | 1.0437 | 1.0815 |

| target | model MAE | poisson | median | constant | form |
|---|---|---|---|---|---|
| home_goals | **0.9489** | 0.9549 | 0.9897 | 0.9968 | 1.0409 |
| away_goals | 0.8583 | 0.8628 | **0.7892** | 0.8965 | 0.9672 |

**Two results the model does not win**, both now surfaced in `metrics.json` and
on the Model page:

1. The team-strength Poisson **calls more results correctly** (47.3% vs 46.0%).
   The model's only edge over it is a marginally better log loss. A 55-feature
   gradient-boosted ensemble that cannot out-call a textbook Poisson on result
   accuracy has not yet earned its complexity.
2. The median still beats the model on away-goals MAE (0.789 vs 0.858). This is
   expected — MAE is minimised by the median and Premier League away goals have
   a median of 1 — but it is reported rather than omitted.

**Walk-forward backtest, 3 completed seasons, 114 folds, 1,140 matches:**

| season | matches | correct | exact | log loss | always-home |
|---|---|---|---|---|---|
| 2023-24 | 380 | 59.5% | 9.2% | 0.9334 | 46.1% |
| 2024-25 | 380 | 52.6% | 9.7% | 0.9916 | 40.8% |
| 2025-26 | 380 | 47.9% | 10.5% | 1.0562 | 42.6% |
| **all** | **1140** | **53.3%** | **9.8%** | **0.9937** | 43.2% |

**Read this carefully.** 53.3% is *higher* than the 46.0% holdout figure, and
that is not evidence the model is better than the holdout said. The backtest
refits before every matchweek, so a late-season fold has been trained on that
same season's earlier rounds; the holdout model has never seen the season it is
scored on. They measure different conditions and are deliberately kept as
separate figures — blending them would hide which is which.

**Confidence calibration** — the check was whether low-confidence calls really
are wrong more often. They are; this one is a positive result:

| bucket | n | observed |
|---|---|---|
| 0–40% | 111 | 36.9% |
| 40–50% | 376 | 46.5% |
| 50–60% | 270 | 54.4% |
| 60–70% | 229 | 59.0% |
| 70–80% | 113 | 66.4% |
| 80–100% | 41 | 85.4% |

Monotonic and close to the diagonal, mildly overconfident in the 70–80% band.

## N5 — Dashboard

**Changed:** `pages/Dashboard.jsx`, `pages/ModelPage.jsx`, `pages/Predict.jsx`,
`pages/Analytics.jsx`, `pages/Teams.jsx`, `components/Sidebar.jsx`, `App.jsx`,
`theme.js`, new `hooks/`, `components/dashboard/UpcomingFixtures.jsx`,
`components/predict/{Select,UpcomingSelector}.jsx`,
`components/model/{RetrainPanel,ModelArchitecture}.jsx`.

- **Added the upcoming-fixtures panel.** `/fixtures/upcoming` had been serving
  371 live fixtures all along; nothing on the dashboard consumed it and
  `/fixtures/current` was called from nowhere in the app.
- `Predict.jsx` hardcoded `season: "2025-26"` on submit, so once 2026-27 began
  every prediction was filed against the wrong season. Now taken from the
  fixture feed.
- `UpcomingSelector` had **no empty state**: an empty feed rendered two
  `<select>`s with no options and a dead button, with nothing explaining why.
  That is what "upcoming fixtures don't display" looked like from the user side.
  The component that *did* handle it, `PredictionCard.jsx`, was dead code.
- `ModelPage` read `exact_score_count` / `correct_result_count` / `wrong_count`
  from the top level of `/analytics/model/performance`, where they do not exist
  — they live under `live_settled`. All three defaulted to 0, so the donut
  rendered three empty slices beside a non-zero "Evaluated" count.
- The "Model Architecture" block was hardcoded to "35 engineered features",
  "Home Goals + Away Goals" and "80/20 walk-forward split". The real model has
  55 features, 12 target models and a season-holdout split. It now reads
  `/model/metrics`, so it cannot drift again.
- **Responsive layout.** The app had zero media queries, an unconditional 220px
  sidebar margin and hard `gridTemplateColumns`, so everything squeezed instead
  of reflowing. Added breakpoints, an off-canvas drawer below `md`, and grids
  that collapse to one column.
- **The calibration panel could never have rendered.** `parseBuckets` looked for
  `data.buckets` / `data.calibration` and field names like `predicted_prob` and
  `observed_freq`. The endpoint returns `calibration_buckets` with
  `confidence_range` / `predictions` / `actual_hit_rate_pct` — so none of the
  several shapes it "defensively" accepted was the real one. It reported
  "not yet measured" even against a completed 1,140-match backtest. Found only
  by loading the page after the backtest had run; the endpoint returning 200
  had looked like proof enough. Fixed, and the chart now draws all six buckets.
- Backtested and live-settled accuracy presented as separate, labelled figures.
- Removed 460 lines of dead code (`PredictionCard`, `HistoryTable`,
  `TeamStats` — ~19% of frontend source, none imported anywhere). Split
  `Predict.jsx` (279 lines) per the ~200-line convention.

## N6 — Cleanup

- `_result` and `_outcome_sign` existed as four copies across three routers;
  consolidated into `routers/outcomes.py`.
- Removed `shap==0.45.0` — imported nowhere.
- Removed the dead `possession` row from `Predict.jsx`'s stat table. Neither
  source publishes possession and the model does not predict it; the row was
  inert only because the renderer skips undefined keys.
- The `xgboost` pin drift (`requirements.txt` 2.0.3 vs runtime 2.1.4) resolved
  itself once the image was rebuilt from the pinned file — `metrics.json` now
  records 2.0.3.

**Deliberately not done:** the dead `home_xg` / `away_xg` / `home_possession` /
`away_possession` columns are still in the schema. Nothing writes a non-NULL
value to them and no feature list references them, so they are inert; dropping
them needs a migration against a live volume for no functional gain. Recorded
here rather than done quietly.

## N7 — Verification

- `pytest tests/ -v` in the container: **34 passed** before this pass, including
  every leakage test, and they were re-run after the `TeamIndex` refactor
  specifically because that change touches the point-in-time path.
- Added `tests/test_finalisation.py` covering the non-destructive refresh, the
  partial-season detection, retrain single-flight, the real Poisson baseline,
  the median verdict, the deduplicated outcome helpers, and `TeamIndex`
  returning exactly the rows and order a full-frame scan would.

**Final suite: 53 passed.**

**Verified in the browser** at 1366px: the dashboard renders the performance
band (46.0%, "+2.6 · marginal"), the calibration scatter against the diagonal,
the upcoming-fixtures panel with real MW1/MW2 kickoffs, and the provenance strip
(2026-27, 99.7%, "1 min ago", feed connected). The Predict page loads fixtures
and files them under **2026-27**. The Model page shows backtested and
live-settled figures separately, reads its architecture block from the artefact,
and carries the amber "away goals loses to the median baseline" note.

**A retrain was triggered from the browser** and ran to completion: the button
disabled to "Training…", progress advanced through "building feature matrix" to
"trained away_shots_ot · 6/12 models · 566s elapsed" with a determinate bar, and
finished with metrics regenerated. At 566s the old synchronous implementation
would already have exceeded the browser's timeout and reported failure.

**Not verified:** the narrow-viewport layout. `resize_window` reported success
but the captured viewport stayed 1366px, so the breakpoints, drawer sidebar and
collapsing grids are implemented and compile but have **not** been seen
rendering below `md`. That is the one item in N5 taken on trust.

A degenerate test fixture is also worth recording: the first version of
`test_poisson_is_not_a_copy_of_the_constant_baseline` used two perfectly
mirrored teams, whose strength rates make the two baselines' errors coincide at
exactly 2.0. It failed against correct code. Replaced with four asymmetric teams.

---

## Corrections to existing documents

- `CLAUDE.md` claimed the API base is hardcoded in nine files. It was already
  centralised in `config.js`; it is now `/api` via a build arg.
- `REBUILD_PLAN.md` recorded 44.7% correct result and 1.0611 log loss. The
  measured figures are 46.0% and 1.0413.
- `REBUILD_PLAN.md` marked P10 Done. It had never produced a stored result.
- `DEFECT_CORRECTION_PROMPT.md` (March) is superseded: matchweeks are correct
  (max 38 per completed season) and dates are ISO.


---

# Round 2 — Data integrity, dashboard visualisation, deployment (2026-08-24)

## D1 — Settlement and team-list integrity

**The reported defect.** `Bournemouth vs Man Utd` (2025-26) showed "pending" in a
completed season. Prediction id 15 carried `matchweek=35`; the fixture is stored at
**matchweek 31, 2026-03-20, 2-2**. `settle_predictions` joined on
`(home_team, away_team, season, matchweek)`, so the disagreement meant the join
matched nothing and the row could never settle — with the score sitting in the same
table.

Verified before changing the key: `(season, home_team, away_team)` is **unique
across all 2,849 stored rows** in both divisions. Matchweek contributed no
identifying power while being the one field likely to disagree between what the UI
submitted and what ingestion recorded. Key is now `(season, home_team, away_team)`
plus `division = "E0"`; settlement also **corrects** the prediction's matchweek to
the fixture's, so History stops displaying MW35 for a match played in MW31.

**Measured:** 12 predictions were unsettled; **10 settled** on the first run. The 2
that remain are genuinely unplayed 2026-27 fixtures — correct behaviour, not a
residual bug. Id 15 now reads `2-2`, MW31.

**Second defect, found while confirming the first.** `GET /teams` was a bare
`distinct()` over `home_team` with **no division filter**, returning **47 clubs**
including Wrexham, Plymouth, Millwall, Bristol City, Charlton, Preston and Sheffield
Weds. Those are `division='E1'` rows that `data/promoted.py` adds deliberately so
promoted clubs have prior form instead of NaN — a feature-engineering input that was
leaking into the user's picker. Now **30 clubs**, filtered through a new
`db/teams.py`. `POST /predict` also rejects a club with no top-flight history.

**A correction to the plan.** The plan proposed deleting predictions 4 and 24
(`Arsenal vs Coventry`, `Hull vs Man Utd`) as impossible fixtures. **That was wrong.**
Checking the live feed before deleting: Coventry and Hull are genuinely promoted into
the 2026-27 Premier League, and `/fixtures/upcoming` returns exactly 20 clubs
including both. Those predictions are legitimate and were settled against real
Premier League results. Nothing deleted. This is also why the division filter is the
right mechanism rather than a hardcoded club list — a promoted side becomes
selectable the moment it actually plays a top-flight match.

## D2 — Dashboard visualisation

The dashboard had **no chart at all**, while `GET /model/backtest` was already
returning `by_matchweek` — **114 scored matchweeks** across three seasons, each with
the model's correct-result rate and the always-home baseline for the same fixtures —
and `by_season`. None of it was rendered anywhere in the app.

Added, all reading data that already existed:

- `AccuracyTrend.jsx` — the headline chart. 114 points, model against baseline,
  season boundaries marked, smoothed over a trailing 5-week window because a
  matchweek is only 10 matches and swings on sample size alone. Trailing, not
  centred, so no point is computed from weeks that had not happened yet. The raw
  weekly value stays in the tooltip so the smoothing hides nothing.
- `SeasonComparison.jsx` — per-season bars with the edge stated per season.
- `GoalsTrend.jsx` — scoring shape of the selected season, reusing the `league`
  payload Dashboard already fetches rather than issuing a second identical request.
  This is also what finally makes the season selector drive more than one panel.
- `hooks/useBacktest.js` — three panels read the same payload; the in-flight promise
  is cached at module scope so they share one round trip. `invalidateBacktest()` is
  called after a backtest run so the siblings do not keep showing the old result.
- `components/charts/chartTheme.js` — shared axis/grid/tooltip styling, series
  colours and the rolling-mean helper. The `theme.js` brand-vs-semantic separation is
  preserved: chart series draw from brand tokens because a line identifies a series,
  it does not judge it.

**What the chart shows, which is not flattering.** The model's edge over
always-home **declines season on season: +13.4 → +11.8 → +5.3 points**
(59.5% / 52.6% / 47.9% against 46.1% / 40.8% / 42.6%). The 53.3% headline is an
average that hides a downward trend. The chart is not smoothed until this
disappears; the per-season figures are printed underneath it.

**Palette.** Page headers and chart series moved onto PL purple `#37003c` and PL
green `#00ff85`. `ModelPage`'s bars were two greys, so two different measurements
read as one series in two shades. Analytics' goals chart was green-vs-red, which
made away goals look like a bad outcome rather than a category.

Calibration needed less than planned — it was already a reliability curve with a
diagonal, so it only needed recolouring onto brand.

## D3/D4 — Deployment

- `backend/seed/` — committed 6.5MB snapshot: `epl.db` (2,849 matches, 1,140
  backtested predictions) and twelve trained `.pkl` models. `.gitignore` and
  `.dockerignore` negations scoped to this path only, so working artefacts stay
  ignored.
- **Test predictions cleared from the shipped snapshot.** A deployed instance's
  live-settled accuracy should reflect its own users, not 28 rows of local testing.
- `backend/entrypoint.sh` — restores the snapshot **only when the target is empty**.
  Never overwrites: on a host with a real volume, what is there is newer than the
  image and must win. A restore that clobbered a live database would look exactly
  like a successful boot.
- `backend/Dockerfile` — non-root uid 1000 (HF Spaces grants no root; the previous
  root-owned `/app` would have failed on its first write), `$PORT`, LF-normalised
  entrypoint.
- Workflows: `ci.yml` (63 tests + `npm ci` build + an assertion that the seed
  snapshot is still tracked) and `deploy-backend.yml`, which **polls the deployed
  `/health` until it answers** rather than reporting success on a completed push.
- `frontend/vercel.json` — the `/api` rewrite that keeps the app same-origin, so
  `config.js`, the bundle and the CORS posture are untouched.

**Verified from a wiped volume:** `docker compose down -v && up --build` → entrypoint
logs `restoring baked snapshot`, `Database up to date: 2849 records`, and `POST
/predict` answers **200 immediately** instead of 503. Restart logs `existing database
kept` — the no-clobber guard holds. Container runs as `uid=1000(appuser)`.

**63 tests pass** (53 previous + 10 new in `tests/test_integrity.py`).

## Not done, deliberately

- **The narrow-viewport layout is still unverified.** Carried over from round 1:
  `resize_window` refuses the requested bounds in this environment, so the
  breakpoints compile and are wired but have not been *seen* rendering below `md`.
- **Nothing is deployed yet.** The configuration is written and locally verified;
  creating the HF Space, setting `HF_TOKEN`/`HF_SPACE` and connecting Vercel are
  account actions that need the owner.


---

# Round 3 - Division separation, dashboard rebuild, HF CLI deploy (2026-08-24)

## R1 - The two leagues were blended everywhere they were reported

Reported by the user ("Hull and Coventry on top of the table"), confirmed in code:
`backend/routers/analytics.py` had **no division filter anywhere**. Its only filter
was `MatchResult.season == season`, so every figure downstream was computed over
both divisions:

- The 2025-26 "Premier League" table returned **44 clubs**, including Wrexham,
  Millwall, QPR, Bristol City, Charlton, Oxford, Derby and Portsmouth.
- **Coventry ranked 1st on 46 games played and 95 points** - its E0 and E1 matches
  summed into one row. Hull 4th on 46.
- "Matches played" read **470**, not 380, so avg goals/game and every win rate used
  the wrong denominator.
- `/head-to-head` and `/team/{team}/form` had the same gap.

This is the same class of bug as the `/teams` leak fixed in round 2, in the
endpoints nobody re-checked afterwards. The fix is therefore a **boundary**, not a
filter per handler: `db/teams.py` now owns `division_filter`, `resolve_division`
and `is_played`, and every reporting query goes through it.

**Three further defects surfaced during the sweep, all mine:**

1. **`_is_matchweek_corrupted` wiped the whole database on boot.** It checks
   `max(matchweek) > 38` across *all* divisions; the Championship's 46 rounds read
   as corruption, so the guard truncated `match_results` and reseeded - and since
   the reseed re-adds those same 46-round rows, it would have done it again on
   **every boot, forever**. Now scoped to E0.
2. **`refresh_current_season` deleted the whole current season** and re-inserted
   Premier League fixtures only, so every 6-hourly refresh destroyed the in-progress
   Championship season. It runs on boot, which is why the 2026-27 E1 rows kept
   vanishing minutes after being seeded. Now scoped to E0.
3. **`enrich_season` iterated every row in the season** regardless of division, so
   enriching E0 walked 932 fixtures against a 380-row file and reported 552
   "unmatched". Worse, the loop *writes* `fixture.division`, so it was one
   name/date collision away from relabelling a second-tier match as top-flight.

**An unknown division returned "no data" rather than an error.** `?division=E7`
and `?division=` both fell through to `WHERE division = 'E7'`, matched nothing, and
returned "No played matches for this season and division" - indistinguishable from
a season that genuinely has none. This bit immediately: a `<select>` rendered
before its options had loaded sent an empty string, and the dashboard showed blank
cards with no error anywhere. `resolve_division` now 400s on an unknown division and
treats empty as the default.

## R1b - Both leagues, all seasons

The user then asked for both tables across all seasons. The Championship data
stored at that point was **not a league**: `promoted.py` pulls only the matches
involving clubs about to be promoted - **90 rows of a 552-match season**, and only
for two seasons. A table built from that would have been confidently wrong.

`data/championship.py` now ingests complete E1 seasons from football-data.co.uk.
Result: **3,876 Championship matches** across all 8 seasons (7 complete at 552, plus
the in-progress 2026-27), de-duplicated against the existing fragments - 2024-25 and
2025-26 added exactly 462 each, which is 552 minus 90.

Rounds are **derived**, not sourced: the E1 files carry no gameweek, which is why
every Championship row previously sat at `matchweek=0`. Fixtures are ordered by date
and cut into blocks of twelve. This is an approximation and is labelled as one - a
postponed fixture lands in a later block than the round it belonged to. The league
table does not depend on it at all.

**This changes model inputs.** `strength.py` uses Championship rates to seed a
promoted club's first top-flight attack/defence rating and its starting Elo. That
seed is now computed from a full 46-match season rather than whichever handful the
fragment held. A retrain was run and the metric delta is reported rather than
absorbed.

## R2 - Season and division actually filter

`season` was accepted on `/analytics/league` alone, so the dashboard's selector
drove 2 of 8 panels. Added as optional parameters (defaulting to current behaviour)
to `/analytics/model/performance`, `/predictions/history`, `/model/backtest`, and
`division` to `/teams/by-division`, `/fixtures/recent`, `/fixtures/season/{season}`,
`/team/{name}/stats`. New `/divisions` reports the leagues actually present with
their match counts.

Asking `/model/backtest` for a season the backtest did not cover returns the covered
seasons rather than an empty chart, so the UI can say which seasons exist instead of
rendering a blank panel that looks like a failure.

## R3 - The dashboard is a dashboard

The rule applied: **the summary fits one screen, detail lives below the fold.**
Previously the first viewport held a header, one 290px performance band and the top
40px of a chart - nothing comparable was ever on screen together.

Above the fold at 1366x768: header (52px) + six-card summary strip (96px) + the two
charts that answer "is it working" and "can I trust the probabilities", side by side.
Verified in the browser.

- `ui/MetricCard.jsx` - one card for "a number with a label". There had been three
  visual languages for this (KpiCard, Card+Stat, bare divs), so three pages read as
  three products. Carries a signed delta chip that goes neutral grey below a
  threshold, so +2.6 points does not wear the same confident green as +12.
- `ui/InfoTip.jsx` - the caveats moved here rather than being deleted. Opens on
  hover **and** focus/click, so they are not unreachable by keyboard or on touch.
  Full prose still lives on the Model page.
- `ui/DataTable.jsx` - one table treatment; numerics right-aligned with tabular
  figures, which is the difference between a column of scores being comparable and
  not.
- `dashboard/LeagueTable.jsx` - both divisions, switched by a tab that makes the
  boundary visible.
- `dashboard/SummaryStrip.jsx` - replaces ModelPerformanceBand; the verdict
  paragraph is now a delta chip plus an info tip.

Three honesty fixes found while building it:

- **"Loading" and "absent" rendered identically.** The backtest card read "no
  backtest" for the second the request was in flight - the app asserting an absence
  it had not established.
- **A 78% home-win rate from 9 matches** was rendered in the same type at the same
  size as a 380-match figure. Below a third of a season the card now says
  "small sample" and the info tip says it will move substantially.
- With the Championship selected, the model cards say **"Premier League model"** -
  they describe a model that has never seen a Championship match.

## R4 - Deploy from the CLI

`scripts/deploy-hf.sh <owner>/<space>` - creates the Space, stages, uploads, then
**polls the deployed `/health` until it answers**. Uses the current `hf` CLI and
detects the deprecated `huggingface-cli`, telling you how to upgrade rather than
failing on a missing subcommand. The token comes from an `hf auth` session or
`$HF_TOKEN`; it is never pasted and never written to disk.

`scripts/stage-space.sh` is shared with `deploy-backend.yml`, so the manual and CI
paths are byte-identical rather than two copies that drift. It fails loudly if
`backend/seed/` is missing - a Space deployed without it boots fine and then answers
503 on `/predict`.

## Tests

**76 pass** (63 previous + 13 in `tests/test_divisions.py`): the top-flight filter
excludes E1 and vice versa, NULL divisions count as top-flight, a club present in
both divisions is counted once per division, an unknown division is rejected rather
than returning empty, unplayed fixtures are excluded from aggregates, and derived
Championship rounds fall in blocks of twelve without reordering rows.

---

# Feature-build performance pass — 2026-08-25

## The report

"Training the model in production: over 500 seconds elapsed and training has not
yet started."

## What was actually happening

Not a hang. `GET /model/jobs` on the deployed instance showed a live retrain:

```
"state":"running", "stage":"building feature matrix",
"started_at":"2026-08-25T06:04:42Z", "updated_at":"2026-08-25T06:04:42Z"
```

`updated_at` equal to `started_at` seventeen minutes in — the job had reported
progress exactly once, on entry. It did finish: `finished_at` 06:21:46, **17m 04s**,
of which roughly fifteen minutes preceded the first estimator. The operator was
reading a truthful stage label that happened to be true for a quarter of an hour.

The cost was in `build_training_matrix`. Every window helper filtered the whole
match frame with a boolean mask — `df[(df["home_team"] == team) & (df["date"] <
before)]` — then took `.tail(5)`. A dozen of those per fixture, over 4,570
Premier League fixtures in an 11,218-row frame, is roughly 55,000 full-frame
scans plus the pandas object overhead each carries.

Measured locally on the 6,545-match snapshot, before any change:

| | |
|---|---|
| `build_training_matrix` | **356.28 s** |
| top cost under cProfile | `Series.__init__` 93.8s cumulative, `frame.__getitem__` 110.1s, `guess_datetime_format` 20.4s |

`guess_datetime_format` is the tell: `_rest_days` and `_matches_in_window`
re-parsed the same few thousand date strings tens of thousands of times.

## What changed

**`backend/data/history.py` (new).** The frame is already chronological, so the
rows a team-scoped helper may see are a *prefix* of that team's rows — a binary
search, not a scan. `MatchHistory` groups the frame once (per club, per venue,
per fixture pairing), then serves numpy slices. Windows are capped at ten rows
because nothing longer can reach an output.

**`backend/data/features.py`.** The helpers now read slices instead of carving
frames. `TeamIndex` is gone, replaced by `MatchHistory`. `iterrows()` is gone.
The build reports progress every 250 fixtures.

**`backend/models/backtest.py`.** Each fold predicts its fixtures as one batch;
it was calling `model.predict()` twice per fixture, paying the fixed per-call
cost 2,280 times for a three-season run. `_confidence` is handed
`dict(zip(FEATURE_COLS, X[i]))` instead of a 75-column `Series.to_dict()`.

**`backend/jobs.py`, `routers/model.py`, `RetrainPanel.jsx`.** Jobs now carry a
`unit`, because one job counts different things as it goes. The panel was
hardcoded to "models", which was wrong for every stage but the last — and the
last stage was never the slow one.

## Proof the results did not change

`build_training_matrix` was run under the old implementation and the output
pickled, then re-run under the new one and compared column by column:

```
new build_training_matrix: 1.50s  shape (2669, 75)
old baseline:              356.28s  shape (2669, 75)
speedup: 237x

All 75 columns identical across 2669 rows.
```

Identical, not close: exact float equality with NaN treated as equal to NaN.
`tests/test_feature_index.py` keeps the old boolean-scan implementations as a
reference and asserts the indexed path matches them for every team at every
fixture date in a generated season — including the NaN cases, where `_safe_mean`
skipped missing statistics and a NaN result scored zero points.

## Measured after

On the running container, with the full **4,570-fixture** dataset production has:

| | before | after |
|---|---|---|
| feature matrix (production-sized) | ~15 min | **~5 s** |
| full retrain, end to end | 17m 04s | **57 s** |
| backtest, 3 seasons | ~23 min | **10m 57s** |
| feature matrix (local 6,545-match snapshot) | 356.28 s | **1.50 s** |

The backtest's remaining 649 seconds are 228 estimator fits — two per matchweek.
That is what a walk-forward backtest *is*, not an inefficiency, so it was left
alone and given per-matchweek progress instead.

Accuracy is unchanged, which is the point:

```
1,140 matches over 2023-24, 2024-25, 2025-26
53.6% correct results | RPS 0.1999 | log loss 0.9811
bookmakers' line on the same fixtures: 54.2% | always-home: 43.2%
```

## `/data/refresh` — the same defect, one layer along

Refresh was still a blocking POST: two upstream downloads plus reconciliation,
held open for the whole run. Longer than a browser or the CDN in front of it
will hold an idle connection, so the operator console reported a failed request
for work that was still running, and never showed its result.

It is a background job now — `POST /data/refresh` answers **202 in 0.14 s** with
a job id, `GET /data/jobs/{id}` polls it, `GET /data/refresh` re-attaches after a
reload. `lifecycle.refresh_live_data()` also took a lock: the HTTP path is
single-flight through `jobs.submit()`, but that could not see the in-process
3-hourly timer, and refresh deletes and re-inserts the season's rows — two
overlapping runs would each read a table the other had half-emptied.

Verified end to end against the running stack:

```
POST /data/refresh -> 202 in 0.140s
{"status":"refreshed","played_fixtures":10,"statistics_attached":10,
 "predictions_settled":0,"season":"2026-27"}
```

## Tests

**193 pass** in the container (`docker exec epl-predictor-backend-1 python -m
pytest tests/ -q`), up from 176: `tests/test_feature_index.py` is new (17 tests)
and `TestTeamIndexPreservesSemantics` became
`TestMatchHistoryPreservesSemantics`, covering venue orientation, the
strictly-before cut, the division split and both directions of head-to-head.

Frontend builds clean with `CI=true npm run build`.
