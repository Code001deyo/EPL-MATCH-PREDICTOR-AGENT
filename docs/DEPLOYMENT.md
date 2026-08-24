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

## Admin access

The public site is predictions plus the read-only views. Anything that can change
the model or the data — retrain, backtest, data refresh — requires an admin.

Credentials live in **environment variables, not the database**: the free instance
has no persistent disk, so an accounts table would reset to the baked snapshot on
every restart and admins created after a deploy would silently disappear.

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

`ADMIN_API_KEY` also goes in GitHub → Settings → Secrets → Actions, and the API
base URL in Settings → Variables as `API_BASE_URL`, so the refresh workflow can run.

**Auth fails closed.** With those variables unset, admin endpoints return 503 and
nobody can retrain — including you. A missing secret must never be read as "no
authentication required". The public site is unaffected.

**There is no password reset.** One account, reachable from the internet, with no
lockout beyond a rate limit — a self-service reset would be a bigger hole than it
closes. Losing the password means editing the env var again.

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
