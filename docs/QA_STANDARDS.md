# Quality standards

Every standard here is enforced by something that runs. A standard nobody can
fail is a preference, and this project has already been bitten by one: the
assertion that guarded the data refresh lived inside a YAML `run:` block, no test
suite executed it, and it was wrong for eleven days while every scheduled run
failed and nothing else noticed.

So each rule below names what enforces it. Where nothing enforces a rule yet,
that is stated rather than left implied.

---

## 1. Correctness

| Rule | Enforced by |
|---|---|
| The backend suite passes. No skips added to make it pass. | `pytest tests/` — CI job **Backend tests** |
| New behaviour ships with a test that fails without it | Review |
| A bug fix ships with a test that reproduces the bug | Review |
| A contract another system depends on is asserted in the suite, not only in the caller | `tests/test_refresh_contract.py` is the worked example |

**Current: 243 backend tests, 13 frontend tests.** The count may only go up.

### The contract rule, specifically

If a workflow, a cron, or another service parses one of our responses, the shape
it parses belongs in the test suite. `POST /data/refresh` changed from a
synchronous body to a background job and the workflow that read it was not
updated; nothing failed until the schedule ran, and then it failed silently-ish
for eleven days. `tests/test_refresh_contract.py` now asserts both halves — the
response shape and the decision made about it.

---

## 2. Honesty about data

These are the rules this codebase already lives by. They are listed because they
are quality standards, not stylistic ones — breaking them produces software that
is confidently wrong, which is worse than software that is visibly broken.

| Rule | Enforced by |
|---|---|
| Missing means missing. Never substitute a constant for an absent measurement | `tests/test_integrity.py`, review |
| Never blend distinct statuses into a derived bucket | Review |
| An empty state says "not measured", never renders a 0 | `EmptyState` component; `TitleRace.test.js` |
| A reconstruction is labelled as a reconstruction | `db/race.py` `kind`; `TitleRace.test.js` |
| A model's misses are reported as plainly as its hits | `test_notifications.py` |
| No invented movement. A chart may only move because the data moved | Fixed seeds per matchweek in `season_history.py`; `test_season_sim.py` |
| Probabilities that must sum to a whole number are asserted to | `test_season_sim.py` |

### Never verify a deploy by how it behaves

The free Render instance is burstable: the same unchanged endpoint measured
10.6s, then 1.5s, then 7–9.5s within one hour. That is a larger swing than most
changes being verified. Ask `/health` for the commit it was built from.

---

## 3. Accessibility

The floor, not the ambition. All of it is measured by
`frontend/scripts/responsive-check.js`.

| Rule | Threshold | Why this number |
|---|---|---|
| Control tap targets | ≥ 44 × 44 px | Apple HIG and Material both land here; below it a thumb misses |
| Inline text links | ≥ 24 px | WCAG 2.2 AA (2.5.8) minimum. The standard explicitly exempts inline targets from the larger figure, because enlarging a link inside a sentence breaks the sentence |
| Keyboard focus | Always visible | `:focus-visible` in `styles/app.css` |
| Colour is never the only signal | Text equivalent required | Several clubs share a palette; every title-race row carries `.pl-sr-only` prose |
| Motion | Honour `prefers-reduced-motion` | CSS media query; **and** JS-driven SVG animation disabled, because CSS cannot reach it |

The tap-target rule deliberately distinguishes controls from inline links. A
check that flags every footer link produces noise nobody reads, which is worse
than not checking.

---

## 4. Responsive layout

`npm run qa:responsive` — 3 pages × 6 viewports = 18 combinations.

**Widths:** 320, 375, 768, 1024, 1440, 1920.

**Why headless rather than by hand:** a Chrome window on Windows will not go
narrower than about 500px, and the development display is 1366 wide. By hand,
neither a phone nor a large desktop is reachable. This was not a hypothetical —
the dashboard scrolled horizontally at 320 and 375 and nobody could have seen it
by resizing a window.

Each combination asserts:

1. **The body never scrolls horizontally.** Wide content scrolls inside its own
   box. This single check catches most responsive breakage.
2. **No element is wider than the viewport**, and the failure names the element.
   "The page is 40px too wide" is not actionable.
3. **No console errors.** A component that compiles and then throws on mount is a
   blank white page and a green build.
4. **Tap targets meet section 3.**
5. **The page rendered text.** A blank body overflows nothing and would otherwise
   pass every check above.

Screenshots land in `frontend/screenshots/` (gitignored) for the eye check no
assertion replaces.

### The two failure modes this found

- A grid item defaults to `min-width: auto`, so it will not shrink below its
  content. One long kickoff label held a dashboard column at 612px inside a
  320px viewport. Every grid track now has a zero minimum.
- `ResponsiveContainer` with a `minWidth` inside an `overflow-x: auto` parent is
  a resize feedback loop: the container widens, the parent gains a scrollbar, the
  observer fires again. It locked the renderer until it stopped answering.

---

## 5. Code shape

| Rule | Enforced by |
|---|---|
| Files split by domain at ~200 lines, barrel re-export, unless there is no natural seam | Review |
| A table has exactly one writer | Review — `models/fixture_prediction.py` exists for this reason |
| Comments explain why, not what | Review |
| No hardcoded league membership, seasons or club lists | Review |

The one-writer rule earned its place: `predictions` has an invariant of one row
per fixture, and when the notifier needed to write that table the upsert was
extracted rather than copied. Two writers drift, and the drift is what put the
same match in History twice.

---

## 6. Release gates

Nothing reaches `main` without all of:

- [ ] **Backend tests** green
- [ ] **Frontend build** green — includes `npm test`
- [ ] **Frontend QA** green — `npm run qa:responsive`
- [ ] **Seed snapshot present**

After a deploy, and before calling it done:

- [ ] `/health` reports the commit that was pushed. Not latency, not "it looks
      different" — the SHA.
- [ ] `retrain-model.yml` has been run. **A deploy resets the models**: the free
      tier has no persistent disk, so `entrypoint.sh` restores the baked
      `backend/seed/` models onto empty storage, silently reverting any retrain
      since the image was built. Match data in Neon is unaffected.
- [ ] The deployed pages have been diffed against the capture taken *before* the
      release. It is the only check that catches content quietly going missing.
- [ ] `npm run qa:responsive https://<production-url>` is clean.

---

## 7. What is not yet enforced

Listed so the gaps are visible rather than assumed covered.

- **No automated colour-contrast check.** Contrast was chosen by hand and has not
  been measured. An axe-core pass in the responsive checker would close this.
- **No end-to-end test of email delivery.** The dispatcher is tested against a
  stub mailer. A real message has still not been proved to arrive, but the
  failure is no longer invisible: `POST /notifications/selftest` reports which
  settings are present and returns the provider's verbatim rejection, so
  "unverified domain", "wrong key" and "nobody subscribed" are now three
  distinguishable answers rather than one silent False.
- **No load or performance budget.** The bundle size is not tracked and no page
  has a time-to-interactive target.
- **The Championship is not simulated.** The stored fixture list covers the
  Premier League alone; a season cannot be played out without knowing which
  matches remain. This is a data gap, not a bug.
- **No visual regression baseline.** Screenshots are captured but not compared
  against a previous run, so a layout that changes silently still passes.
