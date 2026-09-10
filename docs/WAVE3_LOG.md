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

---

## Design review round (2026-09-09)

Seven changes, from a review of the deployed site.

**Em dashes gone.** 49 files, all rendered text and every email. Removed from
user-facing strings and from the `-` placeholder used for a missing value.
Comments still contain them; they are not rendered and sweeping them would be a
large diff with no visible effect.

**The circled-i tooltips are gone.** They read as small badges beside every
heading. The context they held is not lost: the standings became a real table
with scoped headers, which does the job the hidden per-row sentence was doing.

**Subscribe copy cut.** Three paragraphs to two lines. The one caveat kept is the
timing one, because it is a promise being made to someone deciding to sign up.

**Real club badges.** The official crests from the Premier League CDN. The URL
keys on an **Opta** id, which is not the id PulseLive puts in fixture payloads
(Arsenal is `1` there, `t3` on the CDN), so `data/clubs.py` syncs it from
`/teams` into a `clubs` table. Not hardcoded: a hardcoded map goes wrong the
summer three clubs are promoted, and goes wrong silently, as a club wearing
another club's badge. 36 clubs across 13 seasons, all resolved, so relegated
clubs keep their badge in history.

These crests are trademarks and that is true whatever the project is for. The
decision to use them for a non-commercial build is recorded in `db/clubs.py`
rather than quietly dropped, and nothing is copied into the repository - the page
points at the source. The drawn monogram stays as the fallback for a club the
sync has not seen and for a CDN that stops answering.

**Real tables.** Position, badge, club, then numbers right-aligned with tabular
figures so a column reads down rather than cell by cell. Scoped `<th>` so a
screen reader says "Arsenal, Points, 9". Below 620px the least load-bearing
columns are dropped rather than every column being squeezed. Crests on the league
table and the fixture list too.

**Previous seasons.** A season picker, with 2024-25 and 2025-26 reconstructed in
full, locally and in production. A past season needs no fixture list:
`match_results` is complete for it. Their timestamps come from the results
instead, at 19:00 UTC on the day of a matchweek's last match - approximate in the
hour, exact in the day, and only ever used to place a point on a time axis.
Without it every point of a past season carried the moment the backfill ran and
the season collapsed onto a single day.

`simulate-race.yml` gained a season input, because the workflow could only
reconstruct the current campaign and a deployed instance therefore had one season
in its picker while local had three.

### Two defects the checks caught, not the eye

- **Goal difference had never been returned.** Stored since the first version,
  absent from `series()`, so the standings rendered an empty GD column for every
  club.
- **The new select and segmented buttons were 36px** against the project's own
  44px control rule. Rather than bulk them up on desktop, the rule now applies
  where it belongs: 44px under `pointer: coarse`, the WCAG 2.5.8 floor of 24px
  otherwise, with the checker asking the same question. A CSS ordering mistake
  meant the first attempt silently did nothing, which the checker also caught.

### Verified

- 243 backend, 15 frontend, 18/18 viewports, locally and against production.
- Frontend `8b5fb55e` and backend `c8f57e27` confirmed live by commit, not by
  latency.
- Local and production render byte-identical race pages (2,597 characters at
  1920px on both). The earlier 4,554 was the pre-table layout; the table is
  denser, not missing anything.
- Zero em dashes in the deployed JavaScript bundle.

---

## Privacy, copyright, smooth curves, automatic retraining (2026-09-09)

### Privacy policy

`/privacy`, written from what the code does rather than from a template. Every
claim is checkable against `db/subscribers.py` (what is stored), `mailer.py`
(where it goes) and `routers/subscribe.py` (how it is collected). A policy that
describes a different system from the one running is worse than none, because it
is a promise nobody is keeping.

It is specific about the awkward part: unsubscribing marks the row rather than
deleting it, so a later import cannot quietly re-add someone. Erasure is offered
on request. Linked from the sidebar, from the subscribe box where consent is
actually given, and from every email footer.

Email footers now carry sender, unsubscribe and policy. Missing any of the three
reads as spam to a filter and to a person. The confirmation email has its own
footer with no unsubscribe link, because there is nothing to leave until an
address confirms.

### Copyright

`COPYRIGHT.md` plus a footer notice, separating the two things that get
conflated. The software, model and interface belong to Hanova Technologies; the
match data does not and is not claimed, with sources and terms listed. Club
crests are shown from the Premier League CDN and remain the clubs' trade marks:
no licence has been granted, which is a different position from being licensed
and matters if this is run commercially. The drawn fallback badges stay in the
tree so that is a one-component change.

### Smooth curves

Monotone at every resolution and dots off, matching the accuracy and scoring
trends elsewhere on the site. The steps caveat would then have been describing
something no longer on screen, so it says what is true instead: each point sits
at the moment its matchweek finished, and the curve between two points is drawn
for readability rather than as a claim about the days in between.

### Retraining without an operator

Retraining was something someone remembered to do, so the model sat on old data
for as long as nobody thought about it and nothing on the site said so.

`models/training_state.py` records the matchweek a model was trained through.
`POST /model/retrain-if-stale` decides; the schedule stays ignorant of
matchweeks, the same split the notification cron uses. It answers 200 and does
nothing when the model is current, because retraining an unchanged model spends
ten minutes of a 0.1 vCPU instance producing identical estimators.

A matchweek counts as complete at 8 of 10 fixtures played. Not 10: one
postponement would otherwise hold the watermark back for a week, and the nine
that were played are real evidence.

On success the operator is emailed the figures rather than "retrain complete". A
notice with no numbers in it teaches the reader to stop opening it, and the point
is that a bad retrain should be noticeable.

The watermark lives beside the model files, so a deploy restoring the baked seed
models clears it. That is correct rather than a bug: after a deploy the running
model is the older one and does need retraining. Asserted, along with a watermark
from last season not vouching for this one, which would otherwise suppress
retraining for an entire campaign.

### Verified in production

```
before   trained_through_matchweek: null   stale: true
run 1    retrained
after    trained_through_matchweek: 3      behind_by: 0   stale: false
run 2    {"status":"up-to-date"} - did nothing
```

Both halves proved live: it fires when it should and stays quiet when it should
not. Frontend and backend both on `a1dee553`, confirmed by commit. 253 backend
tests, 15 frontend, 18/18 viewports against production, `/privacy` serving 200.

### Still outstanding

- `VERCEL_TOKEN` is still not a repository secret, so the frontend ships only
  from a logged-in CLI.
- `ADMIN_EMAIL` (or `RESET_EMAIL_TO`) is not set on Render, so the retrain notice
  logs loudly instead of sending. The retrain itself is unaffected.
- No subscriber email has been proved to arrive; the sending domain is unverified
  in practice.

---

## Closing the three loose ends (2026-09-09) - role: deployment engineer

### The mail problem was not the configuration

`mailer.send()` returned a bare bool. When Resend rejected a message the reason
went to a `print` in a container log, on a free instance that sleeps. From
outside the process, an unverified sending domain, a wrong API key and simply
having no subscribers were the same observation: nothing arrived.

So diagnosis came first. `send()` now returns a `SendResult` carrying `ok`, the
HTTP status and the provider's own wording. It defines `__bool__`, so every
existing `if send(...)` caller is unchanged - including the dispatcher's
rollback, which deletes the send-log row on failure so the next tick retries
rather than recording a delivery that never happened. That has its own test,
because a richer return type is exactly the kind of change that quietly breaks
it.

`POST /notifications/selftest` reports which settings are present, by name and
boolean only, and optionally sends one message and returns what the provider
said. Presence rather than values: answering "is this configured" should not
require reading the secret to find out whether the secret exists.

### What the diagnosis found

Nothing was broken. **Resend accepted the message on the first try**, HTTP 200,
`provider_id 52925ad0-64fe-41a0-aa17-91bda93ef8d0`, and it arrived. The sending
domain was verified all along. The reason this had never been proved is that
nobody had tried and nothing would have reported it if they had.

### Render configuration

`configure-service.yml` sets `ADMIN_EMAIL`, `RESET_EMAIL_TO` and
`PUBLIC_SITE_URL` through the Render API using the existing `RENDER_API_KEY`.
All three are non-secret and live in the file so the configuration is reviewable
rather than sitting in a browser session.

It uses `PUT /v1/services/{id}/env-vars/{key}`. The bulk form at `/env-vars`
replaces the entire list and would have wiped `RESEND_API_KEY`,
`ADMIN_PASSWORD_HASH`, `SESSION_SECRET` and `DATABASE_URL`. The destructive call
is one path segment shorter than the safe one, which is why the warning sits next
to it in the workflow.

**The first run failed, correctly.** Setting an environment variable through the
Render API does not restart the service: three variables accepted with HTTP 200
at 15:58, no deploy created, and the backend still could not see two of them a
minute later. The workflow had polled `/health`, which was the wrong question -
the old container answers 200 perfectly well, it is simply running the previous
configuration. It now triggers a deploy, waits for `live`, and then asks the
running process what it can actually see. "The API accepted the value" and "the
process can read it" are different claims.

### A vulnerability found by walking the path

`POST /subscribe` built the confirmation link from `request.headers["origin"]`.
Send somebody else's address with `Origin: https://evil.example` and the service
mails **them** a link to the attacker's site carrying a valid confirm token -
the one credential that activates a subscription.

It also broke the ordinary case: any client sending no Origin produced
`/api/subscribe/confirm?token=...` with no host, a dead link in the one message
that has to work.

Now built from `PUBLIC_SITE_URL`, with a test pinning it. Found by preparing to
prove subscriber mail end to end rather than by reasoning about it, which is the
argument for actually walking a path.

### Verified

- Mail self-test: accepted by Resend **and confirmed received**.
- All required settings visible to the running process:
  `RESEND_API_KEY`, `ADMIN_EMAIL`, `RESET_EMAIL_TO`, `PUBLIC_SITE_URL` all true.
  `NOTIFY_EMAIL_FROM` is unset, so the sender falls back to
  `EPL Predictor <noreply@hanovatechnologies.co.ke>`, which Resend accepts.
- 258 backend tests, 18/18 viewports.
- Backend live on the pushed commit, verified by `/health`.

### Still open

- **`VERCEL_TOKEN`** is not a repository secret. It is a credential and is not
  mine to create or store. Until it is set, the frontend deploys only from a
  logged-in CLI.
- **The subscriber confirmation flow** has been triggered for a fresh address and
  is waiting on the link being opened. `/subscribe/status` reported one confirmed
  subscriber before this, so the path has worked before; this run proves it again
  with the Origin fix in place.

---

## Responsiveness and accessibility (2026-09-10)

### What "18/18 green" actually meant

Three pages at six widths. The app has nine public pages and an operator console.
The number had been quoted all day as if it meant the site was responsive.

It is 128 checks now: nine public pages plus the console, at eight viewports,
with two interactive states, and an accessibility pass per page.

### The one live bug automation could not see

`min-height: 100vh` on the app shell and the sidebar. On a mobile browser `100vh`
is the viewport *without* the address bar, which is part of the screen until you
scroll - so the last centimetres of every page sat underneath it at rest.

Headless Chrome cannot catch this. There is no address bar in a headless
viewport, so every green run had been silent about it. Fixed with `100dvh` and a
`100vh` line above it, as a class rather than an inline style because a React
style object cannot hold the same property twice and the fallback is the point.

### A layout rule that hid a control

The column-hiding rule under 620px was written for the race table's nine columns
and applied to every `.pl-table`. On the subscriber list column five is Actions,
so an operator on a phone could read the list and had no way to unsubscribe or
erase anyone. Scoped to `.pl-table--race`, and the table stacks below 720px using
a treatment that had been in the stylesheet unused since it was written.

The check written for it was wrong on the first attempt: it asked the *control*
whether it was hidden, but an element inside a `display:none` subtree keeps its
own computed display, so the answer was always no. It asks the cell now. Verified
by putting the bug back, watching it fail, and taking it out again - a regression
test that has never failed has not been tested.

### 288 contrast violations

`axe-core` now runs per page on four rules. Its first run found 288 colour
contrast failures.

The fault was at the token level, and the theme file had already written down the
rule it was breaking: brand colours decorate, semantic colours carry meaning.
Brand colours were being used as type. `#00ff85` as text on white measures
**1.34:1** - not readable by anyone. `slate400` measured 2.56:1 and was the
muted-text colour in 57 places.

Two of my own mistakes on the way, both the same mistake: darkening `slate400`
fixed the white pages and broke the purple sidebar, and a global swap of the
brand green turned the sidebar's link dark-on-dark. A token used on two
backgrounds must satisfy the darker one or have a sibling for the other surface.
Hence `onNavyMuted` and `blueText`.

The largest single cause was drift the stylesheet warned about in its own header:
`--slate-400` in `app.css` still held the value `theme.js` no longer used.

Also fixed: five password fields on the console and two on the sign-in page had
labels sitting beside their inputs rather than associated with them.

### Local and production reach different states

Two faults appeared only against production. The sign-in page had never been
loaded by the sweep, because production does not accept this machine's admin key
and served the sign-in form where local served the console. And `semantic.neutral`
failed only where a delta happened to be neutral, which local's data never was.

Running the sweep against one environment checks one environment.

### Verified

- **128/128** locally and against production, zero accessibility violations.
- `dvh` confirmed by measurement at a 375x400 viewport, not by a screenshot.
- Frontend verified live by its `build-commit` tag at `298428bb`.
- 271 backend tests, 15 frontend.

### Deliberately not done

**Visual regression.** The plan called for a pixel baseline. 128 full-page
screenshots is a large binary baseline to carry in git, and charts vary
sub-pixel between runs, so a naive comparison cries wolf and gets switched off. A
scoped version - two pages at two widths, above the fold only - would carry most
of the value at a fraction of the weight. Left as a decision rather than
half-built.

**Real devices.** Headless Chromium is not Safari. Dynamic viewport behaviour,
momentum scrolling and input zoom-on-focus all differ, and `100dvh` is exactly
the kind of thing worth confirming on a real iPhone.
