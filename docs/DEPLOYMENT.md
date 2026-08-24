# Deployment

Free hosting for both halves, with `git push origin main` as the deploy trigger.

```
                    GitHub: Code001deyo/EPL-MATCH-PREDICTOR-AGENT
                                     |
                  push to main ------+------ push to main
                        |                          |
                        v                          v
          GitHub Actions                    Vercel (native integration)
          deploy-backend.yml                root directory: frontend/
                        |                          |
                        v                          v
          Hugging Face Space                 Static CRA bundle
          (Docker, FastAPI)                        |
                    ^                              |
                    |     /api/* rewrite,          |
                    +---- proxied server-side -----+
```

The browser only ever talks to the Vercel origin. Vercel proxies `/api/*` to the
Space, so the bundle contains no host-specific URL and there is no CORS surface.
This is the same shape as local development, where nginx proxies `/api` to the
backend container — one architecture, two adapters, rather than a production-only
code path that nothing tests.

## Why these platforms

**Backend — Hugging Face Spaces, Docker SDK, CPU Basic.** 2 vCPU / 16GB RAM, free,
no idle spin-down. It is the only genuinely free tier that can run this workload:
a full retrain fits twelve XGBoost models and peaks well above Render's free-tier
512MB ceiling. Render was rejected for that reason, not for convenience — its free
web services also cannot attach a persistent disk and spin down after 15 minutes
idle. Fly.io was rejected because its free allowance is now trial credit that runs
out.

**Frontend — Vercel.** Static hosting plus the server-side rewrite that keeps the
app same-origin. Netlify and Cloudflare Pages would both work identically; Vercel
is chosen for the rewrite syntax and the zero-config CRA build.

## Setup

### 1. Hugging Face Space

Create a Space: SDK **Docker**, hardware **CPU basic (free)**. Then in GitHub →
Settings:

| Kind | Name | Value |
|---|---|---|
| Secret | `HF_TOKEN` | An HF access token with **write** scope |
| Variable | `HF_SPACE` | `owner/space-name` |

The token is only ever read from the environment inside the workflow. It is never
written to a file, never echoed, and the push command redirects its output so a
failure cannot print the URL it is embedded in.

### 2. Vercel

Import the repo, set **Root Directory** to `frontend`. Then edit
`frontend/vercel.json` and replace `REPLACE-ME` with the Space host — `owner/space-name`
becomes `owner-space-name.hf.space`, lowercased — and push. See `frontend/VERCEL.md`.

### 3. Deploy

**First deploy, or any manual push** — from your machine:

```bash
pip install -U huggingface_hub     # provides the `hf` CLI
hf auth login                      # or: export HF_TOKEN=...
./scripts/deploy-hf.sh <owner>/<space-name>
```

If `hf` is "not found" straight after installing it, pip put it in a per-user
scripts directory that is not on PATH — it prints a warning about this that is
easy to miss. The deploy script looks in that directory itself (including the
Windows `%APPDATA%\Python\PythonXY\Scripts` form, converted with `cygpath` for
Git Bash), so it will find a correct install even when your shell cannot.

The script creates the Space if it does not exist, stages the tree, uploads it,
then **polls the deployed `/health` until it answers** and prints the host to put
in `frontend/vercel.json`. It reads the token from your `hf auth` session or
`$HF_TOKEN` — it never asks you to paste one and never writes one to disk.

Note the CLI was renamed: `huggingface-cli` is deprecated in favour of `hf`. The
script detects an old install and tells you how to upgrade rather than failing
with a missing-subcommand error.

**Every deploy after that** — `git push origin main`. CI runs the tests first; the
backend deploy waits on them and then polls `/health` the same way, so the job only
goes green when the deployed API is actually up.

Both paths stage the Space with the **same** `scripts/stage-space.sh`, so what you
push by hand and what CI pushes are byte-identical. That script also fails loudly
if `backend/seed/` is missing, because a Space deployed without it boots fine and
then answers 503 on `/predict` — a silent, delayed failure.

## Limits that will actually be hit

These are measured or documented constraints, not hypotheticals.

**The Space has no persistent disk.** Everything written at runtime — the SQLite
database, retrained models — is lost when the container restarts. This is handled
by `backend/seed/`: a committed 6.5MB snapshot (2,849 matches, 1,140 backtested
predictions, twelve trained models) baked into the image and restored by
`backend/entrypoint.sh` **only when the target directory is empty**. A restart
therefore comes up instantly with a working `/predict` rather than spending
several minutes re-seeding and answering 503 in the meantime.

**The baked model goes stale.** The 6-hourly refresh loop keeps *fixture data*
current, but it does not retrain. A deployed instance that nobody retrains is
serving a model frozen at the last build, and after a restart any retrain done
through the UI is gone. Refreshing the snapshot is a deliberate act: retrain
locally, re-copy `backend/seed/`, commit. Nothing in the deployment does it for
you, and nothing pretends otherwise.

**Spaces pause after ~48 hours of inactivity.** The next visitor waits for a
container restart. The baked snapshot makes that a restart rather than a re-seed,
but it is not instantaneous.

**Vercel's proxy has an edge response timeout** in the tens of seconds. Nothing
the UI calls exceeds it: retraining returns `202` with a job id in ~0.2s and the
browser polls `/model/jobs/{id}`. Any *synchronous* long endpoint added later will
time out at the proxy while succeeding on the backend — the precise failure that
made a successful 321-second retrain report "Retrain failed". Keep long work
behind the job API.

**Image size is 1.55GB**, dominated by XGBoost, pandas and scipy. HF builds it
remotely, so a first deploy takes several minutes.

**The database now carries two divisions.** 2,669 Premier League matches and 3,876
Championship matches. The Championship is present because promoted clubs need real
prior form instead of NaN on matchday one, and because the app reports both tables.
Every reporting endpoint takes a `division` parameter defaulting to `E0`; the model
is trained and scored on `E0` only.

## Rolling back

The Space mirrors `main` and is force-pushed on each deploy, so it holds no
independent history. To roll back, revert on GitHub and push — that is the only
supported path. Editing the Space directly works until the next deploy silently
overwrites it, which is why its generated `README.md` says so.

Vercel keeps every build; a previous deployment can be promoted from its dashboard
without touching the repo.

## Local development is unchanged

```bash
docker compose up -d --build     # http://localhost:3000
```

Backend port 8000 is not published — the browser reaches it through nginx at
`/api`, the same way it reaches the Space through Vercel in production.
