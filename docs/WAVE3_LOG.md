# Wave 3 — work log

What was actually done, measured, and left undone. Appended at the end of each
phase, before the next begins. Figures here are observed output, not intent.

Branch: `wave3-refresh-notifications-race`.

---

## Phase 1 — the refresh workflow (2026-09-09) — **Done, verified in production**

### What was wrong

"Refresh live data" had failed every scheduled run since 29 August — eleven days,
88 runs. Every failure was byte-identical:

```
{"job_id":"ed79a8a20b00","state":"running","started":true, ...}
::error::unexpected refresh status
```

`POST /data/refresh` became a background job in `0b952225`: 202 with a job id,
the outcome delivered later on `/data/jobs/{id}`. `refresh-data.yml` was never
updated and went on grepping the old synchronous body for `"status": "refreshed"`.
`retrain-model.yml` *was* converted to poll at the time; refresh was missed.

**The refreshes were succeeding the whole time.** What was lost was the
confirmation — and with it, any way to notice one that genuinely failed. That is
the part worth fixing, not the alarm.

### What changed

- `refresh-data.yml` starts the job, polls `/data/jobs/{id}` to a terminal state,
  then checks the job's **result** — a job reaching `succeeded` is not the same as
  a season having been refreshed. Polling also keeps a sleeping free instance
  awake for the job's duration, which the fire-and-forget POST never did.
- Handles the join case: 200 with `started:false` means a refresh was already in
  flight. That is success, not an error.
- The decision moved out of YAML into `backend/scripts/check_refresh.py` and into
  the suite (`backend/tests/test_refresh_contract.py`, 10 tests). This is the
  actual fix: the broken assertion survived eleven days because it lived somewhere
  nothing runs. Placed under `backend/` rather than `.github/` so the container can
  reach it too — inside the container `backend/` is `/app` and `.github/` does not
  exist.

### Audit of the other workflows

Checked for the same class of drift, since one had already slipped through.
`ci.yml` and `deploy-backend.yml` make no calls against our own API.
`deploy-render.yml` and `deploy-vercel.yml` poll the Render and Vercel APIs and
already handle terminal states correctly. **`refresh-data.yml` was the only one.**

### Verified

Run [34283031813](https://github.com/Code001deyo/EPL-MATCH-PREDICTOR-AGENT/actions/runs/34283031813),
dispatched against the live Render instance:

```
[2] succeeded  complete
refresh status: refreshed
{"current_season":"2026-27","matches_played":78,
 "latest_match_date":"2026-09-06","last_refreshed":"2026-09-08T21:54:20+00:00"}
```

Every step green. `last_refreshed` stamped at run time confirms the work happened
rather than being reported.

---

## Phase 2 — kickoff as a real instant (2026-09-09) — **Done**

### Why

Nothing downstream could be scheduled. `_parse_fixture` read PulseLive's
`kickoff.millis`, converted it to a `YYYY-MM-DD` date and **discarded the time** —
enough to order history, not enough to say when a match starts.

Worse, upcoming fixtures were stored nowhere at all.
`ingestion.refresh_current_season` filters to played matches before writing, by
design, and `routers/teams.upcoming_fixtures` fetches the rest live on every
request. So there was no row for a notification to reference and no list of
remaining matches for a simulation to run over.

### Deviation from the plan

The plan said to add `kickoff_utc` to `match_results`. That was wrong: that table
holds played matches, and its delete-and-reinsert path is the one this project
already lost a season to (`tests/test_refresh_safety.py` exists because of it).
Widening it to carry unplayed fixtures would have put scheduling data inside the
most dangerous write path in the codebase.

A separate `fixtures` table instead (`backend/db/fixtures.py`), upserted by
`backend/data/schedule.py`, called from `lifecycle.refresh_live_data()` so the
schedule and the results move together. `match_results` is untouched.

Upsert, not delete-and-reinsert: `notification_log` rows point at these fixtures,
and a forgotten "already sent" is a duplicate email.

Schedule sync failure is caught and recorded rather than failing the refresh —
stale fixtures cost a missed alert, an aborted refresh costs stale results.

### Honest gap

`kickoff_utc` is nullable and stays NULL when the league has not fixed a time.
Those fixtures are excluded from the notification queue rather than being given a
guessed 15:00, which would mail people at the wrong time and be indistinguishable
from a real time downstream.

### Verified

Against the live PulseLive feed, in the container:

```
sync: {'status': 'synced', 'season': '2026-27', 'kickoffs_known': 380,
       'kickoffs_unknown': 0, 'inserted': 0, 'updated': 0, 'total': 380}
  MW4 Aston Villa v Nott'm Forest | 2026-09-12T14:00:00+00:00 | 'Sat 12 Sep 2026, 15:00 BST' | U
total stored: 380
```

380 fixtures, every one with a known kickoff. `inserted: 0` because the
container's boot refresh had already run the sync — which incidentally confirms
the `lifecycle` wiring fires on its own.

**Suite: 214 pass, 0 fail** (`docker exec epl-predictor-backend-1 python -m pytest tests/ -q`).

---
