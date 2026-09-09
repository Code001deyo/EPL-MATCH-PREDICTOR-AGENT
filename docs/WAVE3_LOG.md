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

## Phase 3 — subscriptions and notifications (2026-09-09) — **Done, delivery unproven**

Double opt-in (`backend/db/subscribers.py`), a generic-response subscribe endpoint,
server-rendered confirm/unsubscribe pages that work without JavaScript, and a
dispatcher that owns every scheduling decision (`backend/notify/queue.py`).

**Send-once is a unique index, not a check.** `(pl_fixture_id, subscriber_id, kind)`.
The log row is written before the message is handed to Resend and rolled back if
the send fails. A check-then-send would let two overlapping cron ticks both pass.

**The reset path is untouched.** It still mails one fixed address from
`RESET_EMAIL_TO` and never an address a caller supplies.

### Verified

- 19 tests, including two integration tests with a stub mailer: a second dispatch
  tick sends nothing, and a *failed* send is retried on the next tick rather than
  recorded as delivered.
- Live against the running stack: `POST /subscribe` returns the generic body,
  confirm activates and burns the token, a replayed token reports expired,
  `/subscribe/status` moves 0 to 1, and `POST /notifications/dispatch` runs clean.

### Not verified, and why

**No real email has been sent.** `delivery_configured` is `false` locally — there
is no `RESEND_API_KEY` in this environment. The flow is built and the send call is
exercised against a stub, but end-to-end delivery needs:

1. `RESEND_API_KEY` set on Render.
2. A **verified sending domain** on `hanovatechnologies.co.ke`. Resend rejects
   every message until DNS is in place.
3. `PUBLIC_SITE_URL` set, or unsubscribe links render against an empty base.

**The free-tier ceiling is real.** Resend free is 100/day, 3,000/month. A ten-match
day is 20 emails per subscriber, so roughly **5 subscribers before the daily limit
bites**. That is a plan decision, not an engineering one.

**Timing is a window, not ten minutes.** `NOTIFY_PRE_WINDOW_MINUTES` defaults to 20
against a five-minute cron that drifts 5-15 on public runners. The UI says "in a
window before kickoff", which is the honest claim.

---

## Phase 4 — the title race (2026-09-09) — **Done, verified**

`models/season_sim.py` plays the remaining fixtures 10,000 times using the Poisson
rates the existing model already returns, ranked by the real Premier League order,
vectorised in numpy. `models/season_history.py` reconstructs earlier matchweeks so
the curve is not a single point.

### Verified

Live, on the running stack:

```
elapsed 29.4s | MW 3 | remaining 350 | unpriced 0
Man City  50.0% | Arsenal 39.8% | Liverpool 5.5% | Man Utd 2.5%
sum title probs: 1.0    sum top4: 4.0    sum relegation: 3.0
```

Those three sums are the check that matters — exactly one club wins, four finish
top four, three go down — and a ranking bug would otherwise hide behind twenty
plausible percentages. Arsenal's stored curve: 34.8% to 38.0% to 40.5%.

**Defect found and fixed during verification.** Matchweek 3 held both a live and a
backfill snapshot, so `/race/current` returned every club twice and the
week-on-week delta compared a live figure against a reconstruction of the same
week. A live snapshot now supersedes a reconstruction on read; both rows are kept.

### Honest limits, carried into the UI

Fixtures are drawn independently and rates are held fixed, so these are the
probabilities implied by today's model under independence. Real seasons have
injuries, dead rubbers and drift. Reconstructed weeks are shaded and captioned,
because today's model has been trained on the matches it is reconstructing.

---

## Phase 5 — the UI (2026-09-09) — **Built and unit-verified; the visual pass did not run**

- `components/crest/` — monogram shield badges from each club's real colours, in
  SVG. No trademarked artwork is shipped. `crestUrl` per club is the slot for
  licensed assets later. An alias table resolves the spellings the two data
  sources disagree on.
- `styles/app.css` — the app's first stylesheet, for the four things inline styles
  cannot express: media queries, `:focus-visible`, `clamp()` and
  `prefers-reduced-motion`. The app had no hover states and no keyboard focus ring
  because there was no syntax for them, not because they were declined.
- `pages/TitleRace.jsx` + `components/race/` — leaderboard with week-on-week
  deltas, and an area chart with the reconstructed region shaded.
- `components/Masthead.jsx` — season, matches played, and a live "data updated"
  stamp. Not decoration: for eleven days the refresh was failing and every page
  looked exactly as it always had.
- `components/SubscribeCard.jsx` — placed after the two charts that establish
  whether the model is worth following, not before them.

### Verified

11 frontend render tests pass. They catch what a successful build cannot: a
component that compiles and then throws on first render, which in a
client-rendered app is a blank white page rather than a visible error. They also
pin the honesty properties — the reconstruction caveat, the timing caveat, the
screen-reader text equivalent on every race row.

CI now runs those tests; it previously only built the frontend.

Confirmed present in the shipped bundle and stylesheet: `pl-race-row`,
`focus-visible`, `prefers-reduced-motion`, and both caveats.

### Not done

**The breakpoint screenshot pass did not happen.** The Chrome extension is not
connected to this session (`list_connected_browsers` returned `[]`), so the app was
never driven at 320 / 375 / 768 / 1024 / 1440 / 1920 and no screenshots were
taken. The responsive CSS is written — `auto-fill` grids, a card-stacking table
rule below 720px, `clamp()` type, 44px tap targets, a race row that drops its bar
column on narrow screens — but **written is not verified**, and it should not be
called verified until someone has looked at it.

---

## File length

Two files passed the ~200-line convention and were split:

- `models/season_sim.py` (219) — table construction to `models/league_table.py`,
  which also removed a near-duplicate of the same twenty lines in
  `models/season_history.py`. Two copies of a points calculation is two places for
  the simulation's table to drift away from the site's.
- `pages/TitleRace.jsx` (283) — row rendering to
  `components/race/RaceLeaderboard.jsx`, the long-to-wide reshape to
  `components/race/buildSeries.js`.

**Final: backend 243 pass, frontend 11 pass.**

---

## CI (2026-09-09)

All three checks green on PR #1: Backend tests, Frontend build (now including the
new test step), Seed snapshot present.

Three attempts were needed to make `npm ci` accept the lockfile. The cause was
not the dependencies: CI pins Node 20 (**npm 10**) and the lock was being
regenerated with a local npm 11, which dedupes differently — npm 10 then read it
as incomplete (`Missing: yaml@2.9.0 from lock file`) while `npm ci` succeeded
locally. Regenerated with `npx npm@10` and verified the way CI runs it: only
`package.json` and `package-lock.json` in an empty directory, `npm ci`, exit 0.

Passing locally with the wrong npm proved nothing, which is why the first two
fixes were guesses.

---

## Deployment (2026-09-09) — role: deployment engineer

### Pre-release baseline

Captured before anything moved, because a diff against a capture taken afterwards
proves nothing:

| | Before | After |
|---|---|---|
| Backend `/health` commit | `8599536` | `faff52b9` |
| Frontend `build-commit` | `e4172507` | `e4172507` — **not deployed** |
| `/race/current` | 404 | 200 |
| `/subscribe/status` | 404 | 200 |

Note the backend was **four commits behind `main` before this release**, which is
the auto-deploy problem this project already knows about. The deploy moved those
four along with the new work.

### What shipped

- Merged PR #1 as `faff52b9`, all four CI gates green.
- `deploy-render.yml` ran from CI and verified the running code is the commit —
  `/health` reports `faff52b9`. Not inferred from latency: the free instance
  varies 1.5–12s on an unchanged endpoint, which is a wider swing than most
  changes being checked.
- Notification dispatch smoke-tested against production:
  `pre sent=0 post sent=0 errors=0`. Nothing was due — the next fixture is
  12 September — and there are no subscribers, so this proves the pipeline runs
  and sends nothing it should not.

### Two corrections to what was assumed before the deploy

**`RESEND_API_KEY` is already set on Render.** `/subscribe/status` reports
`delivery_configured: true`, so the subscribe box will be *open* in production
rather than closed. Sign-ups will be accepted and a confirmation email attempted.
Whether it arrives depends on the sending domain being verified with Resend,
which has not been proved — no message has been sent to a real address.

**The season simulation ran on boot.** `/race/current` was already answering with
a live matchweek-3 simulation before anything was triggered by hand.

### Blocked: the frontend is not deployed

`deploy-vercel.yml` fails at its configuration check:

```
##[error]Not configured: VERCEL_TOKEN(secret)
```

`gh secret list` confirms only `ADMIN_API_KEY` and `RENDER_API_KEY` exist, and
Vercel's own Git integration did not deploy either push. **Production still
serves `e4172507`**, so the title race page, the subscribe module and the
responsive fixes are live in the API but not visible on the site.

This needs a credential that must not pass through here. The repository owner
should create a token at <https://vercel.com/account/tokens> and set it:

```
gh secret set VERCEL_TOKEN
gh workflow run deploy-vercel.yml --ref main
```

Everything else is ready; this is the only step remaining.

### Cost control applied during the deploy

The notification cron as merged polled every five minutes round the clock. Each
run wakes the Render instance and a wake resets its 15-minute idle timer, so the
instance would never sleep: **720 instance-hours a month against a 750-hour free
allowance** — 96%, with no headroom and no warning before it ran out. Narrowed to
match hours (Sat/Sun 11:00–23:59, weekdays 17:00–23:59 UTC), about 260 hours a
month. A fixture outside those windows gets no email; that gap is deliberate and
costs less than the alternative.

### Post-deploy gates

- [x] `/health` reports the pushed commit
- [x] New endpoints answer 200
- [x] Notification dispatch runs clean against production
- [ ] Retrain — triggered, `retrain-model.yml` run 34324824889
- [ ] Frontend deployed — **blocked on `VERCEL_TOKEN`**
- [ ] Deployed pages diffed against the pre-release capture — cannot complete
      until the frontend deploys
- [ ] `npm run qa:responsive https://novapl.vercel.app` — same

### Frontend deployed — the block cleared

`vercel login` unblocked it. Built locally with `REACT_APP_COMMIT` stamped in and
deployed from source with `--build-env`, mirroring what `deploy-vercel.yml` does,
then aliased to `novapl.vercel.app`.

Deploying the prebuilt `build/` folder does **not** work here: `frontend/vercel.json`
sets a `buildCommand`, so Vercel re-runs it inside the uploaded output directory,
which has no `package.json`, and the deploy fails with exit 254. Deploy from
source and pass the commit through `--build-env`.

Verified the way the workflow verifies it — by the `build-commit` meta tag, not by
a 200. Every non-`/api` path rewrites to `index.html`, so a 200 from `/race`
proves only that the app shell loaded. That is exactly how a missing page went
unnoticed before.

```
[1] serving: 9e0dc9699c9056536192961891ff6d43dea7c60b
VERIFIED: novapl.vercel.app is serving 9e0dc969
```

### The page diff caught a real difference

`npm run qa:responsive https://novapl.vercel.app` passed 18/18, but the race page
measured **3,066 characters against 4,554 locally**. Not a layout fault — the
production database held a single snapshot, so the page correctly rendered
"Only one matchweek stored so far" instead of a chart. The honest empty state was
working; the backfill had simply never run there.

This is the whole argument for diffing deployed pages rather than checking that
they load. Both versions were "working"; only the character count said one was
missing its main feature.

Fixed by `simulate-race.yml`, added for the purpose — a workflow rather than a
documented `curl`, because the admin key is a repository secret and routine work
should not require pasting it into a terminal. Production now holds MW1–MW3 for
every club:

```
MW1  25.1%  [backfill]    MW2  25.9%  [backfill]    MW3  30.6%  [live]
sum of title probabilities: 1.0
```

Re-run: race page 4,561 characters, matching local. 18/18 clean.

### Post-deploy gates — all met

- [x] `/health` reports the pushed commit (`faff52b9`)
- [x] Frontend serves the pushed commit (`9e0dc969`), checked by meta tag
- [x] New endpoints answer 200, through the production proxy as well as directly
- [x] Retrain and backtest completed on production
- [x] Notification dispatch runs clean and sends nothing it should not
- [x] Deployed pages diffed against the pre-release capture — one real difference
      found, explained and fixed
- [x] `npm run qa:responsive` clean against production, 18/18

### Still outstanding

- **`VERCEL_TOKEN` is still not a repository secret.** This deploy went out from a
  logged-in CLI, so the *automated* path remains broken and the next push will not
  deploy the frontend. Setting it is one command: `gh secret set VERCEL_TOKEN`.
- **No email has been proved to arrive.** `RESEND_API_KEY` is set and the subscribe
  box is open in production, but nothing has been sent to a real address, so the
  sending domain is unverified in practice.
