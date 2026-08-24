# Deployment

Free hosting for both halves, with `git push origin main` as the deploy trigger.

```
                    GitHub: Code001deyo/EPL-MATCH-PREDICTOR-AGENT
                                     |
                  push to main ------+------ push to main
                        |                          |
                        v                          v
                 Render (render.yaml)        Vercel (native integration)
                 Docker, free instance       root directory: frontend/
                        |                          |
                        v                          v
                 FastAPI + XGBoost           Static CRA bundle
                        ^                          |
                        |     /api/* rewrite,      |
                        +---- proxied server-side -+
```

The browser only ever talks to the Vercel origin. Vercel proxies `/api/*` to the
backend, so the bundle contains no host-specific URL and there is no CORS surface.
This is the same shape as local development, where nginx proxies `/api` to the
backend container - one architecture, two adapters, rather than a production-only
code path that nothing tests.

## Why these platforms

**Backend - Render, Docker runtime, free instance.** Chosen after measuring the
workload rather than guessing about it: **a full retrain peaks at 237 MiB RSS**, so
the free instance's 512 MB is comfortably sufficient. An earlier revision of this
document rejected Render on the assumption that XGBoost would exhaust that budget.
That assumption was never measured and it was wrong - the feature matrix is
2,669 x 55, and the retrain is slow because of Python loop overhead, not memory.

**Hugging Face Spaces is no longer free for this.** `hf repo create` returns
`402 Payment Required`: "Static Spaces are free for everyone, but hosting Gradio
and Docker Spaces on free cpu-basic requires a PRO subscription." The Space path is
still in the repo (`scripts/deploy-hf.sh`, `.github/workflows/deploy-backend.yml`,
manual trigger only) because it works unchanged on a PRO account and is the better
host when available - 2 vCPU / 16 GB and no idle sleep.

**Frontend - Vercel.** Static hosting plus the server-side rewrite that keeps the
app same-origin. Netlify and Cloudflare Pages would work identically.

## Setup

### 1. Backend on Render

1. Go to <https://dashboard.render.com/blueprints> and choose **New Blueprint**.
2. Connect the GitHub repo. Render reads `render.yaml` and creates the service.
3. Wait for the first build. The image is 1.55 GB, so expect several minutes.

`autoDeploy: true` is set, so every later push to `main` redeploys. No workflow
and no secret is needed - Render pulls from GitHub itself, exactly like Vercel.

The health check is `/health`, not `/health/ready`. `/health` answers within a
second of boot because seeding runs on a background thread; `/health/ready` reports
503 until that finishes, so pointing Render at it would make every deploy look
failed for the length of a cold start.

### 2. Frontend on Vercel

1. Import the repo, set **Root Directory** to `frontend`.
2. Put the Render URL into `frontend/vercel.json`, replacing `REPLACE-ME`, and
   push. See `frontend/VERCEL.md`.

### 3. Optional: Hugging Face instead of Render

Needs a PRO subscription. Set repository secret `HF_TOKEN` and variable `HF_SPACE`,
then run the "Deploy backend to Hugging Face Spaces" workflow manually, or locally:

```bash
pip install -U huggingface_hub     # provides the `hf` CLI
hf auth login                      # or: export HF_TOKEN=...
./scripts/deploy-hf.sh <owner>/<space-name>
```

If `hf` is "not found" straight after installing it, pip put it in a per-user
scripts directory that is not on PATH - it prints a warning about this that is easy
to miss. The deploy script looks there itself, including the Windows
`%APPDATA%\Python\PythonXY\Scripts` form converted with `cygpath` for Git Bash.

## Operator access

The public site is predictions plus the read-only views. Anything that can change
the model or the data — retrain, backtest, data refresh — requires an operator.

**The operator area is at `/secure-model` and is linked from nowhere.** There is no
navigation entry, the public pages make no authentication requests at all, and the
sign-in form and console are code-split into a chunk the public site never
downloads. `/docs`, `/redoc` and `/openapi.json` are disabled unless `ENABLE_DOCS`
is set, because the schema would otherwise list every operator route to anyone who
asked. Source maps are not built, so the source tree is not readable from the
deployed bundle.

**What that does and does not buy you.** It stops the operator area being *found*
by someone browsing the site or reading the API schema. It does not make the URL
secret: a client-rendered app has to know its own routes, so the path is still
present in the main JavaScript bundle and anyone who reads it can find `/secure-model`.
That is acceptable precisely because the path was never the protection —
`require_admin` on the server is, and it holds identically for a caller who knows
the URL and one who does not. Do not treat the path as a credential.

Sign-in and the console share one route: signed out you get the form, signed in you
get the console, and the address bar never changes. A separate `/…/login` would be
a second discoverable path for no benefit.

### Where credentials live, and the rule that matters

Credentials live in the **database**, with the environment used only to create the
first account.

**If `admin_users` is empty, one row is created from `ADMIN_USERNAME` and
`ADMIN_PASSWORD_HASH`. If it is not empty, the environment is ignored.**

That second half is the important one. Without it every deploy would quietly
overwrite a changed password with whatever the env var still said, and the
operator would believe their new password was in effect while the old one kept
working. The consequence is worth stating plainly: **once the account exists,
editing `ADMIN_PASSWORD_HASH` in Render does nothing.**

*Break-glass, if the password is lost and email is unavailable:* delete the row
(`DELETE FROM admin_users;` against the Neon database), set `ADMIN_PASSWORD_HASH`
to a fresh hash from `scripts/make-admin-hash.py`, and restart. The next boot
bootstraps from the environment again.

This requires durable storage, which is why the database moved to Postgres — see
below.

Generate them locally, then paste the output into Render → your service →
Environment:

```bash
python scripts/make-admin-hash.py
```

| Variable | Purpose |
|---|---|
| `ADMIN_USERNAME` | the single admin account |
| `ADMIN_PASSWORD_HASH` | scrypt hash — the password itself is never stored |
| `SESSION_SECRET` | signs the session cookie |
| `ADMIN_API_KEY` | lets the scheduled refresh authenticate without a cookie |
| `ALLOWED_ORIGINS` | comma-separated; defaults to localhost + the Vercel origin |
| `DATABASE_URL` | Neon Postgres connection string. Unset means SQLite on the local disk, which is wiped on every restart |
| `RESEND_API_KEY` | sends the password-reset email |
| `RESET_EMAIL_TO` | fixed recipient for reset links (`hanovatechnologies@gmail.com`) |
| `RESET_EMAIL_FROM` | verified Resend sender, e.g. `EPL Predictor <noreply@hanovatechnologies.co.ke>` |
| `RESET_LINK_BASE` | public site URL used to build the reset link |
| `ENABLE_DOCS` | set to `1` only where you want `/docs` exposed; leave unset in production |

`ADMIN_API_KEY` also goes in GitHub → Settings → Secrets → Actions, and the API
base URL in Settings → Variables as `API_BASE_URL`, so the refresh workflow can run.

**Auth fails closed.** With those variables unset, admin endpoints return 503 and
nobody can retrain — including you. A missing secret must never be read as "no
authentication required". The public site is unaffected.

**There is no password reset.** One account, reachable from the internet, with no
lockout beyond a rate limit — a self-service reset would be a bigger hole than it
closes. Losing the password means editing the env var again.

## Durable storage (Neon Postgres)

Set `DATABASE_URL` to a Neon connection string. That is the whole migration: the
next boot finds an empty database, loads the baked snapshot into it, and creates
the operator account from the environment.

**Two things caught us doing this, both worth knowing:**

*Setting an environment variable through the Render API does not redeploy the
service.* The value appears in the dashboard while the running instance keeps the
environment of its last deploy, so the app carried on using SQLite and a restart
wiped a prediction exactly as before — which looks precisely like "Postgres lost
the data". Always trigger a deploy after changing environment variables, and
confirm from the logs that `[seed] empty database — loading snapshot` appeared.

*Neon's connection URI already carries `sslmode=require`.* Appending another
produces `invalid sslmode value: "('require', 'require')"`. Add the psycopg driver
prefix, and only add `sslmode` if it is absent.

It fixes two things at once. Password changes and reset tokens survive a restart,
which is what makes self-service credentials possible at all. And **predictions
stop being lost** — before this, every restart restored the snapshot and wiped
whatever visitors had predicted, so the public History emptied itself on a
schedule nobody chose.

Neon is free, needs no card, and does not pause on inactivity the way Supabase's
free tier does. It does suspend compute when idle, so the first query after a
quiet spell pays a wake-up; the engine is configured with `pool_pre_ping` so that
surfaces as a reconnect rather than an intermittent 500.

Without `DATABASE_URL` the app runs on SQLite exactly as before, which is what
local development uses. `docker compose --profile pg up -d` starts a local
Postgres to exercise the production path.

## Password reset by email (Resend)

`POST /auth/forgot` mails a single-use link, valid 30 minutes, to the **fixed**
address in `RESET_EMAIL_TO` — never to an address supplied in the request, which
would hand account access to whoever asked. The token is stored only as a hash, so
read access to the database is not enough to complete a reset.

The endpoint answers identically whether or not the account exists. Anything else
turns it into a way to confirm the username.

If Resend is not configured the endpoint still answers the same way, and the
server logs the failure **and the reset link**, so the operator can recover from
the logs while the mail configuration is fixed. It never pretends to have sent
something it did not.

**Verified in production 2026-08-24:** `noreply@hanovatechnologies.co.ke` →
`hanovatechnologies@gmail.com`, status `delivered` in Resend's own record. The
token from that mail was then used once (200), reused (400) and the new password
accepted at login (200).

**The sender domain must be verified.** Resend's test sender only delivers to the
account owner's own address, so before `hanovatechnologies.co.ke` was verified
every reset was rejected with a 403 — and, by design, the endpoint still returned
its normal generic response. The failure was visible **only in the server log**.
That is the intended trade (the endpoint must not confirm which accounts exist),
but it means mail delivery has to be checked from the logs or from Resend, never
from the endpoint's status code.

Domain verification needs three DNS records (a DKIM `TXT` on
`resend._domainkey`, an `MX` on `send`, and an SPF `TXT` on `send`); Resend
reports `not_started` → `pending` → `verified`, and `pending` is not good enough
to send.

## Keeping results current

`.github/workflows/refresh-data.yml` calls `POST /data/refresh` every 3 hours with
`X-Admin-Key`. This exists because the free instance sleeps after 15 minutes idle,
so the in-process 6-hourly loop only advances while somebody is on the site — after
a late kickoff the results would otherwise sit stale until the next visitor arrived.
The workflow wakes the instance first, and fails loudly rather than reporting a
green run that refreshed nothing.

Free: GitHub Actions is unmetered on public repositories. Render's own cron jobs are
a paid feature and are deliberately not used.

## Limits that will actually be hit

These are measured or documented constraints, not hypotheticals.

**The free instance sleeps after 15 minutes of inactivity.** The next visitor waits
roughly a minute for it to wake. This is the real cost of the free tier and there is
no way around it short of paying or pinging the service on a schedule - and a keep-
alive ping burns the same 750 monthly instance-hours it is trying to protect.

**No persistent disk.** Everything written at runtime - the SQLite database,
retrained models - is lost when the instance restarts or wakes. This is handled by
`backend/seed/`: a committed 7 MB snapshot (6,545 matches across both divisions,
1,140 backtested predictions, twelve trained models) baked into the image and
restored by `backend/entrypoint.sh` **only when the target directory is empty**. A
restart therefore comes up instantly with a working `/predict` rather than spending
minutes re-seeding and answering 503 in the meantime.

**The baked model goes stale.** The 6-hourly refresh loop keeps *fixture data*
current but does not retrain, and any retrain triggered through the UI is lost on
the next restart. Refreshing the snapshot is a deliberate act: retrain locally,
re-copy `backend/seed/`, commit. Nothing in the deployment does it for you, and
nothing pretends otherwise.

**Vercel's proxy has an edge response timeout** in the tens of seconds. Nothing the
UI calls exceeds it: retraining returns `202` with a job id in about 0.2s and the
browser polls `/model/jobs/{id}`. Any *synchronous* long endpoint added later would
time out at the proxy while succeeding on the backend - the precise failure that
made a successful 321-second retrain report "Retrain failed". Keep long work behind
the job API.

**Concurrency is fixed but not unlimited.** Measured locally: ten simultaneous
predictions used to return 0 successes and ten `database is locked` errors; they
now return 10/10 in 4.3s, and a single prediction dropped from 4.56s to 0.84s.
Reproduce with `python scripts/loadtest.py <api-base> 10`. Requests still serialise
on one worker, so on 0.1 vCPU expect the same shape at several times the latency.

**Rate limiting is per-process.** It resets on restart and would not be shared
across workers. That makes it a spam brake, not a boundary against a determined
attacker; anything stronger needs shared state this project does not pay for.

**Retrain on the free instance will be slow.** It measures ~250s locally with far
more CPU than 0.1 vCPU. It fits in memory, but expect it to take considerably
longer, and the instance may sleep mid-run if nothing else is holding it awake.

**The database carries two divisions.** 2,669 Premier League matches and 3,876
Championship matches. Every reporting endpoint takes a `division` parameter
defaulting to `E0`; the model is trained and scored on `E0` only.

## Rolling back

Render keeps previous deploys - roll back from the service's Events tab, or revert
on GitHub and push. Vercel keeps every build; promote a previous deployment from
its dashboard without touching the repo.

## Local development is unchanged

```bash
docker compose up -d --build     # http://localhost:3000
```

Backend port 8000 is not published - the browser reaches it through nginx at
`/api`, the same way it reaches Render through Vercel in production.
