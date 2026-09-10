# Security audit, 2026-09-10

The repository was made public to open source the code. This is what the audit
found, what was changed in response, and what was measured afterwards.

Read the headline first, because the length of the remediation list below is not
a measure of how bad the situation was.

---

## No secret has leaked

- **`.env` was never committed.** Only `.env.example`.
- **No credential in any of 109 commits** (76 on `main`, 109 across all refs).
  Every commit was scanned for Vercel, Resend, Render, GitHub, AWS, OpenAI and
  Slack token shapes and for PEM private-key headers. The only match on a loose
  first pass was `re_a_real_looking_secret`, the deliberately fake key in
  `tests/test_mailer.py` that exists to prove the settings object never prints a
  real one. The scan was re-run after the remediation below; still clean.
- **The committed database holds no personal data.** `backend/seed/epl.db`
  contains `match_results` (6,545), `predictions` (0) and `backtests` (1,140).
  No `subscribers`, no `admin_users`, no sessions.
- **Nothing secret reaches the browser.** The only `REACT_APP_*` variables are
  `REACT_APP_API_BASE` and `REACT_APP_COMMIT`, and every `REACT_APP_*` value is
  public by construction.
- **Production is locked where it should be.** `/docs`, `/redoc` and
  `/openapi.json` all 404, and every admin endpoint returns 401 anonymously.

Credentials were rotated anyway, because two Vercel tokens had been pasted into
a chat transcript and a token that has been pasted anywhere is spent.

---

## What was fixed

### Script injection in three workflows (highest severity)

An `inputs` expression was interpolated straight into `run:` shell in
`simulate-race.yml`, `retrain-model.yml` and `configure-vercel.yml`. A dispatch
input carrying a double quote, a semicolon and a trailing comment marker would
have closed the URL string and run as a command, with that job's secrets in
scope. `workflow_dispatch` needs write access, so this was never
anonymously exploitable - but it is the documented GitHub hardening rule, and
the repository now accepts outside collaborators.

Every input now reaches the shell through `env:` as a quoted variable. The same
treatment was applied to two things the original plan did not cover, found while
fixing the first:

- **Secrets in presence checks.** Seven workflows tested for a secret by
  interpolating the secret itself into a `test -n` line, putting its value in the
  shell's command line.
- **Step outputs in `deploy-render.yml` and `configure-service.yml`.** Render's
  API responses were being interpolated into shell. Third-party data reaching a
  shell is the same defect regardless of who supplies it.

A machine check now enforces the rule: no workflow expression appears in any
`run:` block in any of the twelve workflows.

### Least privilege on every workflow

None had a `permissions:` block, so every job ran with the repository default.
All twelve are now `contents: read`. Nothing here writes to the repository - the
deploys go through Render's and Vercel's own APIs.

### Security headers

Only `Strict-Transport-Security` was present, from Vercel's default.
`frontend/vercel.json` now sets a Content-Security-Policy, `X-Frame-Options`,
`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` and
`Cross-Origin-Opener-Policy`.

The CSP is strict rather than copied, and it is worth recording why it can be:

| Directive | Why |
|---|---|
| `script-src 'self'` | The build emits one external bundle and `index.html` has no script of its own. `INLINE_RUNTIME_CHUNK=false` was added to the build command to keep it that way - a runtime chunk inlined by CRA would be blocked and the page would go blank. |
| `style-src 'self'` | No `'unsafe-inline'`. React sets styles through the CSSOM, which CSP does not police, and the stylesheet is a file. |
| `img-src` plus `resources.premierleague.com` | The badge CDN is the only third party the page loads from. `data:` is for the drawn monogram fallback. |
| `connect-src 'self'` | The API is same-origin: `vercel.json` rewrites `/api` to Render, so the browser never sees the backend's hostname. |

It was tested before it shipped, not after: the real build was served locally
with the real headers, and the full QA sweep run against it - 116 page and
viewport combinations, zero console errors, so nothing the app does is being
blocked.

### The operator address

The company's operator address was in `configure-service.yml` and
`docs/DEPLOYMENT.md`. Not a credential, but it is the fixed recipient of
password-reset links, so publishing it narrows an attack on this system to
"compromise this one mailbox". It now comes from the `ADMIN_EMAIL` repository
variable, and the workflow fails if that variable is unset rather than pushing an
empty value to Render.

It is **not** removed from history. Rewriting 109 commits breaks every clone and
permalink, and this is an address the company publishes on its own website.

### `.gitignore`

- Added `*.db`, with a negation after it to keep the committed snapshot. A
  developer's local database is the one file in this project that holds real
  subscriber addresses, and it was one `git add .` from being committed.
- Removed the exception that un-ignored private keys under `frontend/`. It
  protected nothing; no such file was ever tracked.
- Added `*.p12`, `*.pfx`, `*.jks`, `id_rsa*`, `id_ed25519*`, `*.ppk`, `.npmrc`,
  `.netrc`, `_netrc`, `credentials.json`.
- Added `.venv*/`. Local virtualenvs were ignored only by a `.gitignore` that
  pip writes *inside* the virtualenv, which is not a rule this repository
  controls.

Proved with `git check-ignore`: a stray `backend/local.db` and a stray
`frontend/x.key` are ignored; `backend/seed/epl.db` is not.

### The seed database can no longer become a PII leak

`backend/seed/epl.db` is clean today only by accident of timing - it was
generated before the `subscribers` and `admin_users` tables existed. Regenerate
it from a live database and the next push publishes real addresses and a
password hash, and nothing in the build would object.

`backend/db/seed_audit.py` now reads the file directly with sqlite3 and reports
any forbidden table. Three tests in `test_seed_guards.py` cover it, including the
one that matters: the check is pointed at a database that *does* contain
`subscribers` and `admin_users`, and it fails. A guard that has never fired is a
guard nobody has tested.

### Model files are executable code

`joblib.load` is `pickle.load`, and unpickling runs whatever the file tells it
to. The model files under `backend/seed/models/` are committed to a public
repository, so "a pull request edits a model file" and "a pull request runs code
on the deploy host" were the same sentence.

`backend/seed/models/SHA256SUMS` records all twelve,
`scripts/verify_seed_models.py` checks them, and the check runs at the two points
that matter:

- **`entrypoint.sh`, before the copy** - the one boundary a repository-supplied
  model has to cross to reach `joblib.load`. It fails closed: a mismatch aborts
  the boot rather than loading the file. Models written by a retrain never cross
  this boundary and are not checked; they were produced by this process, not
  shipped to it.
- **CI**, so a model changed without its recorded hash is a red check on the
  pull request instead of a discovery on the deploy host.

Proved by altering one byte of `home_goals_model.pkl` and confirming the refusal,
then restoring it and confirming the file is byte-identical.

### Dependencies

`npm audit` went from 58 advisories (2 critical, 32 high) to 32 (0 critical, 17
high), with no change to `package.json` - transitive bumps only. `axios`, the one
that actually ships to a browser, is fixed.

Being straight about the remainder: every one of the 17 remaining highs traces to
`react-scripts`. Create React App is unmaintained, so they have no upstream fix.
They are also build-time only - `svgo`, `postcss`, `webpack-dev-server`,
`workbox`, `nth-check` - and none of them reach a user's browser. `npm audit
--omit=dev` still lists them because CRA is declared a production dependency, not
because it ships. The real remedy is migrating off `react-scripts`, which is a
project of its own and is not pretended to be done here.

`.github/dependabot.yml` now keeps npm, pip and Actions moving, grouped and
monthly, with `react-scripts` ignored so the noise does not bury the rest. A
Dependabot pull request nobody reads is worse than none: it looks like the
problem is handled.

### Licence

`COPYRIGHT.md` said the code was not licensed for reuse, which meant nobody could
legally use what had just been open sourced. The code is now **Apache-2.0**
(`LICENSE`), chosen over MIT for its explicit patent grant and its requirement to
mark changed files. `COPYRIGHT.md` was rewritten so the code is licensed while
club crests, match data and the Hanova name stay excluded - crests are not ours
to license, and Apache-2.0 section 6 excludes trade marks by design.

### Vulnerability reporting

`SECURITY.md` gives a private reporting route through GitHub's draft advisories,
says what is in and out of scope, and states plainly that the published models
and the anonymous read-only API are deliberate rather than findings.

---

## Left open, deliberately

**GitHub secret scanning and push protection are not enabled.** They are free on
public repositories, and push protection is the single best control against the
next leak - it refuses the commit rather than reporting it afterwards. This is a
change to repository settings on the owner's account, so it is handed over rather
than made:

> Settings, then Code security and analysis, then enable **Secret scanning** and
> **Push protection**.

**Infrastructure identifiers appear in public Actions logs** (the Render service
id, Vercel deployment ids). Not secret, mildly useful to an attacker, not worth
obscuring.

**The footer still reads "All rights reserved."** That describes the site's
content and branding, which are not licensed, while the code now is. It is
defensible, but it sits one click from an Apache-2.0 licence, so it is recorded
here as something you may want to reword.

**Open sourcing publishes the model.** A public repository publishes the
approach, the features and the trained artefacts. That is the trade that was
accepted, and no configuration undoes it.

---

## Verification

| Check | Result |
|---|---|
| No workflow expression in any `run:` block | 12 of 12 workflows |
| `permissions: contents: read` | 12 of 12 workflows |
| Backend suite | 274 passed |
| Frontend suite | 15 passed |
| QA sweep against the real CSP | 116 combinations, no console errors |
| Seed PII guard fires on a dirty database | yes |
| Model checksum guard fires on one altered byte | yes |
| `npm ci` on the regenerated lock, clean directory, npm 10 | 941 packages, clean |
| Credential scan, all 109 commits, after the work | clean |
