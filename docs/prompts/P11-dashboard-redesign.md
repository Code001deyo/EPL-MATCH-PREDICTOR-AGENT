# P11 — Dashboard redesign

**Owner:** dashboard-designer
**Depends on:** P7 (provenance), P10 (backtest endpoints) for the accuracy panel

---

## The problem

The dashboard reads as a wall of undifferentiated text. Concretely:

- **Six KPI cards in a flat flex row**, all visually equal weight. Result
  accuracy, goals per game and average confidence are not the same kind of
  number — one judges the model, one describes the league, one describes the
  model's self-assessment — but they are presented identically.
- **All styling is inline objects**, duplicated across six pages. `Card` and
  `SectionTitle` are redefined per file. There is no spacing scale, no type
  scale, and no way to change anything globally.
- **No visual hierarchy.** Every section title is 15px/700. The most important
  thing on the page and the least important look the same.
- **Charts are Recharts defaults** — default grid, default tooltip, default
  legend, no axis units, no empty state.
- **Accuracy shows 0%** on a fresh database and the card cannot distinguish
  "model is wrong" from "nothing has been measured yet". This is the single
  worst failure on the page, because it is actively misleading.

## What to build

A dashboard designed the way an analyst would lay out a monitoring surface:
summary before detail, state encoded in form as well as number.

### Structure

1. **Model performance band** — the primary content, given the most space. Not a
   number in a row of six. Backtested accuracy over the holdout season, the
   baseline it is being compared against, and the delta between them. A model at
   44.7% against a 43.4% baseline must *read* as marginal, not as a green tick.
2. **Calibration** — from `/model/backtest`. Predicted probability bucket versus
   observed frequency, with the diagonal drawn. This is the most informative
   chart available and the current dashboard has nothing like it.
3. **League context** — goals per game, home advantage, form table. Secondary.
4. **Recent predictions** — with the actual result where settled, and a clear
   distinction between "not yet played" and "wrong".
5. **Data provenance** — keep `DataProvenance`, but integrate it rather than
   letting it float above the KPI row as a separate slab.

### Engineering

- Extract a shared design system: tokens for colour, spacing and type in
  `theme.js`, and shared `Card` / `SectionTitle` / `Stat` components under
  `components/ui/`. Remove the per-page redefinitions.
- Keep the Premier League palette in `theme.js` — purple `#37003c`, green
  `#00ff85`. It is the correct brand anchor. Fix its *application*: green is
  currently used both as a brand accent and as the semantic "good" colour, so a
  chart bar and a positive delta are indistinguishable. Separate them.
- Files stay near 200 lines; split by section and re-export.
- Every panel needs three states: loading, empty ("not yet measured"), and
  populated. The empty state must never render as a zero.

## Non-negotiables

**Never show a fabricated or placeholder number.** Absent data renders as "not
measured", never as 0%, and never as a plausible-looking default. This is the
same rule the data layer follows and the reason the backend emits NaN rather
than constants; the interface must not undo it at the last step.

**Do not present a marginal result as a strong one.** The design should make a
1.3-point edge over a baseline look like what it is.

## Acceptance criteria

1. Screenshots of the rebuilt dashboard, populated with real backend data.
2. No inline style objects duplicated across pages; tokens in `theme.js`.
3. Empty states demonstrated — show the dashboard against a database with no
   settled predictions and confirm nothing renders as a misleading zero.
4. The frontend builds clean.
